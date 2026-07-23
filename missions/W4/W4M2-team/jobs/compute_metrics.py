import sys

from pyspark.sql import SparkSession
from pyspark.sql import functions as F

if __name__ == "__main__":
    """
        사용법: spark-submit compute_metrics.py [input_path] [output_path]
        - input_path: clean_trips.py가 저장한 정제된 운행 기록 경로 (기본값 /opt/output/cleaned_trips)
        - output_path: 평균 이동시간/거리 지표를 CSV로 저장할 경로 (기본값 /opt/output/trip_metrics)
    """
    spark = SparkSession \
        .builder \
        .appName("TripMetrics") \
        .getOrCreate()

    input_path = sys.argv[1] if len(sys.argv) > 1 else "/opt/output/cleaned_trips"
    output_path = sys.argv[2] if len(sys.argv) > 2 else "/opt/output/trip_metrics"

    df = spark.read.parquet(input_path)

    metrics_row = df.agg(
        F.round(F.avg("trip_duration_minutes"), 2).alias("avg_trip_duration_minutes"),
        F.round(F.avg("trip_distance"), 2).alias("avg_trip_distance_miles"),
        F.count(F.lit(1)).alias("trip_count")
    ).first()

    # 요구사항: 결과가 사람이 읽기 쉬운 형식으로 표시
    print(f"Trip count: {metrics_row['trip_count']:,}")
    print(f"Average trip duration: {metrics_row['avg_trip_duration_minutes']} minutes")
    print(f"Average trip distance: {metrics_row['avg_trip_distance_miles']} miles")

    # 요구사항: 결과가 사람이 읽기 쉬운 형식으로 저장 - 요약 한 줄짜리 결과라 coalesce(1)로 CSV 한 파일로 저장
    metrics_df = spark.createDataFrame([metrics_row])
    metrics_df.coalesce(1).write.mode("overwrite").option("header", True).csv(output_path)

    spark.stop()
