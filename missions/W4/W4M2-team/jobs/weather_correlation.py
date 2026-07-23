import sys

import pandas as pd
from scipy import stats

from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import DoubleType

if __name__ == "__main__":
    """
        사용법: spark-submit weather_correlation.py [trips_path] [weather_path] [output_dir]
        - trips_path: clean_trips.py가 저장한 정제된 운행 기록 경로 (기본값 /opt/output/cleaned_trips)
        - weather_path: NOAA LCD 시간별 기상 데이터 CSV 경로 - 글롭 패턴 가능
                        (기본값 /opt/data/weather_*_central_park.csv - 여러 해 파일을 한 번에 읽음)
        - output_dir: 결과를 저장할 디렉터리 (기본값 /opt/output/weather_correlation)
    """
    spark = SparkSession \
        .builder \
        .appName("WeatherCorrelation") \
        .getOrCreate()

    trips_path = sys.argv[1] if len(sys.argv) > 1 else "/opt/output/cleaned_trips"
    weather_path = sys.argv[2] if len(sys.argv) > 2 else "/opt/data/weather_*_central_park.csv"
    output_dir = sys.argv[3] if len(sys.argv) > 3 else "/opt/output/weather_correlation"

    # 시간대별 운행 건수 집계 - 날짜+시(hour) 단위로 truncate해서 같은 시각의 날씨 관측과 매칭
    trips_df = spark.read.parquet(trips_path)
    hourly_trips_df = trips_df \
        .withColumn("obs_hour", F.date_trunc("hour", "tpep_pickup_datetime")) \
        .groupBy("obs_hour") \
        .agg(F.count(F.lit(1)).alias("trip_count"))

    # 요구사항: 다양한 파일 형식(CSV) 처리 - NOAA LCD 시간별 관측 데이터 로딩
    weather_raw_df = spark.read.option("header", True).csv(weather_path)

    # LCD 파일 하나에 시간별(FM-15)/일별(SOD)/월별(SOM) 요약이 섞여 있어서 시간별 관측만 골라냄
    hourly_weather_df = weather_raw_df.filter(F.col("REPORT_TYPE").contains("FM-15"))

    # 기온: '*'나 빈 값은 결측치라 매칭 안 되는 행은 자동으로 null 처리(otherwise 없음)
    # 강수량: 'T'(trace, 극미량)와 빈 값은 0.0으로, 값 뒤에 붙는 's'(추정치 플래그)는 떼고 숫자로 변환
    hourly_weather_df = hourly_weather_df \
        .withColumn(
            "temperature_f",
            F.when(F.col("HourlyDryBulbTemperature").rlike(r"^-?\d+$"),
                   F.col("HourlyDryBulbTemperature").cast(DoubleType()))
        ) \
        .withColumn(
            "precipitation_in",
            F.when(F.col("HourlyPrecipitation").isin("T", ""), F.lit(0.0))
             .otherwise(F.regexp_replace(F.col("HourlyPrecipitation"), "s$", "").cast(DoubleType()))
        ) \
        .withColumn("obs_hour", F.date_trunc("hour", F.to_timestamp("DATE"))) \
        .groupBy("obs_hour") \
        .agg(
            F.avg("temperature_f").alias("temperature_f"),
            F.sum("precipitation_in").alias("precipitation_in")
        )

    # 운행 건수와 기상 관측을 같은 시각 기준으로 결합
    # 날씨 데이터는 연도별 파일 전체라, inner join으로 자연스럽게 운행 데이터가 있는 기간으로 좁혀짐
    joined_df = hourly_trips_df.join(hourly_weather_df, on="obs_hour", how="inner").orderBy("obs_hour")
    joined_df.cache()

    print(f"Joined hourly records: {joined_df.count()}")
    joined_df.coalesce(1).write.mode("overwrite").option("header", True).csv(f"{output_dir}/hourly_joined")

    # 요구사항: 통계적 방법으로 상관관계 검증
    # 시간 단위 표본이 한 달 기준 최대 744개뿐이라 driver로 모아서 scipy로 계산
    pdf = joined_df.select("trip_count", "temperature_f", "precipitation_in").na.drop().toPandas()

    temp_corr, temp_pvalue = stats.pearsonr(pdf["temperature_f"], pdf["trip_count"])
    precip_corr, precip_pvalue = stats.pearsonr(pdf["precipitation_in"], pdf["trip_count"])

    # 강수 유무(비/눈 오는 시간 vs 안 오는 시간)에 따라 시간당 운행 건수 평균이 통계적으로 다른지 t-검정
    rainy = pdf[pdf["precipitation_in"] > 0]["trip_count"]
    dry = pdf[pdf["precipitation_in"] == 0]["trip_count"]
    ttest_stat, ttest_pvalue = stats.ttest_ind(rainy, dry, equal_var=False)

    # 요구사항: 결과가 사람이 읽기 쉬운 형식으로 표시
    print(f"Temperature vs trip count: r={temp_corr:.3f}, p={temp_pvalue:.4f}")
    print(f"Precipitation vs trip count: r={precip_corr:.3f}, p={precip_pvalue:.4f}")
    print(f"Rainy hours avg trips: {rainy.mean():.1f} (n={len(rainy)})")
    print(f"Dry hours avg trips: {dry.mean():.1f} (n={len(dry)})")
    print(f"T-test (rainy vs dry hourly trip counts): t={ttest_stat:.3f}, p={ttest_pvalue:.4f}")

    summary_df = spark.createDataFrame(pd.DataFrame([{
        "temp_corr": round(float(temp_corr), 4),
        "temp_pvalue": round(float(temp_pvalue), 4),
        "precip_corr": round(float(precip_corr), 4),
        "precip_pvalue": round(float(precip_pvalue), 4),
        "rainy_hours_avg_trips": round(float(rainy.mean()), 1),
        "dry_hours_avg_trips": round(float(dry.mean()), 1),
        "ttest_statistic": round(float(ttest_stat), 4),
        "ttest_pvalue": round(float(ttest_pvalue), 4),
    }]))
    summary_df.coalesce(1).write.mode("overwrite").option("header", True).csv(f"{output_dir}/stats_summary")

    spark.stop()
