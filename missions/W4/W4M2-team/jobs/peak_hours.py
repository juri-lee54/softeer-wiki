import sys

from pyspark.sql import SparkSession
from pyspark.sql import functions as F

if __name__ == "__main__":
    """
        사용법: spark-submit peak_hours.py [input_path] [output_path]
        - input_path: clean_trips.py가 저장한 정제된 운행 기록 경로 (기본값 /opt/output/cleaned_trips)
        - output_path: 시간대별 운행 건수를 CSV로 저장할 경로 (기본값 /opt/output/peak_hours)
    """
    spark = SparkSession \
        .builder \
        .appName("PeakHours") \
        .getOrCreate()

    input_path = sys.argv[1] if len(sys.argv) > 1 else "/opt/output/cleaned_trips"
    output_path = sys.argv[2] if len(sys.argv) > 2 else "/opt/output/peak_hours"

    df = spark.read.parquet(input_path)

    # 요구사항: "피크 시간대"는 시간당 출발하는 차량 수 기준 - 승차 시각의 시(hour)만 뽑아 날짜 상관없이 집계
    hourly_df = df \
        .withColumn("pickup_hour", F.hour("tpep_pickup_datetime")) \
        .groupBy("pickup_hour") \
        .agg(F.count(F.lit(1)).alias("trip_count")) \
        .orderBy("pickup_hour")

    hourly_df.cache()
    rows = hourly_df.collect()
    peak_row = max(rows, key=lambda r: r["trip_count"])

    # 요구사항: 결과를 사람이 읽기 쉬운 형식으로 표시, 이용 횟수가 가장 많은 시간대 강조
    print("Hourly trip distribution:")
    for row in rows:
        marker = "  <-- PEAK" if row["pickup_hour"] == peak_row["pickup_hour"] else ""
        print(f"  {row['pickup_hour']:02d}:00 - {row['trip_count']:>10,}{marker}")
    print(f"Peak hour: {peak_row['pickup_hour']:02d}:00 with {peak_row['trip_count']:,} trips")

    # 요구사항: 결과를 CSV로 저장 - is_peak 컬럼으로 피크 시간대를 미리 표시해둬서 시각화 단계에서 바로 활용
    result_df = hourly_df.withColumn("is_peak", F.col("pickup_hour") == peak_row["pickup_hour"])
    result_df.coalesce(1).write.mode("overwrite").option("header", True).csv(output_path)

    spark.stop()
