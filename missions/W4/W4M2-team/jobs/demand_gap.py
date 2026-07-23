import sys

from pyspark.sql import SparkSession, Window
from pyspark.sql import functions as F

if __name__ == "__main__":
    """
        사용법: spark-submit demand_gap.py [input_path] [output_path]
        - input_path: clean_trips.py가 저장한 정제된 운행 기록 경로 (기본값 /opt/output/cleaned_trips)
        - output_path: 존별 수요 공백 지표를 CSV로 저장할 경로 (기본값 /opt/output/demand_gap)

        "로보택시 신규 서비스 지역 우선순위 스코어카드"의 1층(수요 공백 탐지) 잡.
        TLC 데이터엔 승객이 실제로 얼마나 기다렸는지(대기시간) 기록이 없다. 대신
        같은 존에서 연속된 두 승차 사이의 시간 간격을 "그 존에서 차를 잡는 데 걸리는
        간격"의 프록시로 쓴다 - 간격이 크다는 건 그만큼 공급이 뜸하다는 뜻.
        주간(06~21시)과 야간(22~05시)을 나눠서 계산해, "밤에 유독 공급이 약해지는 존"을
        찾아낸다(24시간 운행 가능한 무인택시가 메꿀 수 있는 공백).

        주의: 이건 실제 승객 대기시간이 아니라 "완료된 승차 사이의 간격"이라는 프록시다.
        완료된 트립만 있는 TLC 데이터의 근본적 한계 - 요청/취소 기록이 없어서 발생.
    """
    spark = SparkSession \
        .builder \
        .appName("DemandGap") \
        .getOrCreate()

    input_path = sys.argv[1] if len(sys.argv) > 1 else "/opt/output/cleaned_trips"
    output_path = sys.argv[2] if len(sys.argv) > 2 else "/opt/output/demand_gap"

    # 최소 노출량 - 이보다 적은 존은 간격의 90분위수 자체가 표본 부족으로 불안정해서
    # (이전에 5,000건 범죄 샘플에서 스태튼아일랜드가 왜곡됐던 것과 같은 문제) 판단을 보류함
    MIN_TRIPS_PER_BUCKET = 500

    df = spark.read.parquet(input_path)

    df = df.withColumn("pickup_hour", F.hour("tpep_pickup_datetime"))
    df = df.withColumn(
        "time_bucket",
        F.when((F.col("pickup_hour") >= 22) | (F.col("pickup_hour") < 6), F.lit("night")).otherwise(F.lit("day"))
    )

    # 같은 존, 같은 시간대 버킷 안에서 승차 시각 순으로 정렬해 바로 이전 승차와의 간격을 구함
    window = Window.partitionBy("PULocationID", "time_bucket").orderBy("tpep_pickup_datetime")
    df = df.withColumn("prev_pickup", F.lag("tpep_pickup_datetime").over(window))
    df = df.withColumn(
        "gap_minutes",
        (F.unix_timestamp("tpep_pickup_datetime") - F.unix_timestamp("prev_pickup")) / 60.0
    )

    # 각 (존, 시간대) 조합의 맨 첫 승차는 이전 승차가 없어 gap_minutes가 null -> 집계에서 자연히 빠짐
    bucket_df = df.groupBy(F.col("PULocationID").alias("LocationID"), "time_bucket").agg(
        F.count(F.lit(1)).alias("trip_count"),
        F.round(F.percentile_approx("gap_minutes", 0.9), 2).alias("gap_p90_minutes")
    )

    day_df = bucket_df.filter(F.col("time_bucket") == "day") \
        .select("LocationID", F.col("trip_count").alias("day_trip_count"),
                F.col("gap_p90_minutes").alias("day_gap_p90_minutes"))
    night_df = bucket_df.filter(F.col("time_bucket") == "night") \
        .select("LocationID", F.col("trip_count").alias("night_trip_count"),
                F.col("gap_p90_minutes").alias("night_gap_p90_minutes"))

    zone_df = day_df.join(night_df, on="LocationID", how="outer") \
        .na.fill({"day_trip_count": 0, "night_trip_count": 0})

    # 표본이 부족한 존은 비율을 계산해도 신뢰할 수 없어 별도로 표시하고 랭킹 대상에서 제외
    zone_df = zone_df.withColumn(
        "has_enough_data",
        (F.col("day_trip_count") >= MIN_TRIPS_PER_BUCKET) & (F.col("night_trip_count") >= MIN_TRIPS_PER_BUCKET)
    )

    # 값이 클수록 "낮보다 밤에 승차 간격이 훨씬 벌어진다" = 야간 공급 공백이 크다는 뜻
    zone_df = zone_df.withColumn(
        "night_day_gap_ratio",
        F.when(
            F.col("has_enough_data"),
            F.round(F.col("night_gap_p90_minutes") / F.col("day_gap_p90_minutes"), 3)
        )
    )

    zone_df = zone_df.orderBy(F.col("night_day_gap_ratio").desc_nulls_last())
    zone_df.cache()

    total = zone_df.count()
    excluded = zone_df.filter(~F.col("has_enough_data")).count()

    # 요구사항: 결과가 사람이 읽기 쉬운 형식으로 표시 - 표본 부족분은 숨기지 않고 몇 개인지 명시
    print(f"전체 {total}개 존 중 표본 부족(주/야간 각 {MIN_TRIPS_PER_BUCKET}건 미만)으로 판단 보류: {excluded}개")
    print("주간 대비 야간 승차 간격이 가장 크게 벌어지는(=야간 공급 공백이 큰) 존 상위 20개:")
    print(f"{'LocationID':>10} {'day_trips':>10} {'night_trips':>11} {'day_p90_min':>12} {'night_p90_min':>14} {'ratio':>8}")
    for row in zone_df.filter(F.col("has_enough_data")).limit(20).collect():
        print(f"{row['LocationID']:>10} {row['day_trip_count']:>10,} {row['night_trip_count']:>11,} "
              f"{row['day_gap_p90_minutes']:>12} {row['night_gap_p90_minutes']:>14} {row['night_day_gap_ratio']:>8}")

    zone_df.coalesce(1).write.mode("overwrite").option("header", True).csv(output_path)

    spark.stop()
