import sys
import time

from pyspark.sql import SparkSession
from pyspark.sql.types import StructType, StructField, IntegerType, LongType, DoubleType, StringType, TimestampType
import pyspark.sql.functions as F
import glob


# CSV 입력 스키마. 
CSV_SCHEMA = StructType([
    StructField("VendorID", IntegerType(), True),
    StructField("tpep_pickup_datetime", TimestampType(), True),
    StructField("tpep_dropoff_datetime", TimestampType(), True),
    StructField("passenger_count", LongType(), True),
    StructField("trip_distance", DoubleType(), True),
    StructField("RatecodeID", LongType(), True),
    StructField("store_and_fwd_flag", StringType(), True),
    StructField("PULocationID", IntegerType(), True),
    StructField("DOLocationID", IntegerType(), True),
    StructField("payment_type", LongType(), True),
    StructField("fare_amount", DoubleType(), True),
    StructField("extra", DoubleType(), True),
    StructField("mta_tax", DoubleType(), True),
    StructField("tip_amount", DoubleType(), True),
    StructField("tolls_amount", DoubleType(), True),
    StructField("improvement_surcharge", DoubleType(), True),
    StructField("total_amount", DoubleType(), True),
    StructField("congestion_surcharge", DoubleType(), True),
    StructField("Airport_fee", DoubleType(), True),
])


# taxi zone lookup 스키마. 265행짜리 작은 참조 테이블이라 inferSchema로도 되지만,
# inferSchema=True는 스키마 추론을 위해 파일을 한 번 더 스캔하는 Job이 추가로 생기므로
# CSV_SCHEMA와 같은 이유로 명시적으로 정의해서 그 추가 Job을 없앤다.
ZONE_SCHEMA = StructType([
    StructField("LocationID", IntegerType(), True),
    StructField("Borough", StringType(), True),
    StructField("Zone", StringType(), True),
    StructField("service_zone", StringType(), True),
])

MAX_DURATION_MINUTES = 24 * 60
MAX_DISTANCE_MILES = 100
# 이번에 분석하는 파일들이 2024년 데이터라 그 해를 기준으로 상한, 하한을 둠
MIN_PICKUP_YEAR = 2020
MAX_PICKUP_YEAR = 2024

def is_valid(df):
    df = df.filter(
        (F.col("duration_min") > 0) & (F.col("duration_min") <= MAX_DURATION_MINUTES) &
        (F.col("trip_distance") > 0) & (F.col("trip_distance") <= MAX_DISTANCE_MILES) &
        (F.col("fare_amount") > 0) &
        (F.year("tpep_pickup_datetime").between(MIN_PICKUP_YEAR, MAX_PICKUP_YEAR))
    )
    return df
            

def load_input_data(spark, input_dir):
    parquet_path = glob.glob(f"{input_dir}/*.parquet")
    csv_path = glob.glob(f"{input_dir}/*.csv")

    if len(parquet_path) == 0 and len(csv_path) == 0:
        raise FileNotFoundError(f"{input_dir}에 parquet/csv 파일이 없습니다.")

    if len(parquet_path) > 0:
        pq_df = spark.read.parquet(*parquet_path) # parquet은 파일 자체에 스키마가 박혀있어서 자동으로 스키마가 추론됨

    if len(csv_path) > 0:
        # 명시적으로 csv 파일의 스키마 정의 
        csv_df = spark.read.schema(CSV_SCHEMA).option("header", True).csv(csv_path)

    if len(parquet_path) > 0 and len(csv_path) > 0:
        raw_df = pq_df.unionByName(csv_df) # union 대신 unionByName 사용. union은 컬럼 순서로, unionByName은 컬럼 이름으로 합침
        return raw_df
    elif len(parquet_path) > 0:
        return pq_df
    else:
        return csv_df
    

def write_single_csv(lines, header, final_csv_path):
    with open(final_csv_path, "w") as f:
        f.write(header + "\n")
        for line in lines:
            f.write(line + "\n")


def main():
    input_dir = sys.argv[1] if len(sys.argv) > 1 else "/opt/data"
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "/opt/output"

    spark = SparkSession.builder.appName("taxiAnalysis").getOrCreate()

    raw_df = load_input_data(spark, input_dir)

    cleaned_df = raw_df.na.drop(subset=["tpep_pickup_datetime", "tpep_dropoff_datetime", "trip_distance", "fare_amount"])

    cleaned_df = cleaned_df.withColumn(
        "passenger_count",
        F.when((F.col("passenger_count").isNull()) | (F.col("passenger_count") == 0), 1)
        .otherwise(F.col("passenger_count"))
    )
    
    cleaned_df = cleaned_df.withColumn(
        "duration_min",
        (F.col("tpep_dropoff_datetime").cast("long") - F.col("tpep_pickup_datetime").cast("long")) / 60.0
    )
    
    cleaned_df = cleaned_df.withColumn(
        "pickup_date",
        F.date_format(F.col("tpep_pickup_datetime"), "yyyy-MM-dd")
    )
    
    cleaned_df = is_valid(cleaned_df)

    cleaned_df.cache()

    pipeline_start = time.time()

    multi_passenger_df = cleaned_df.filter(F.col("passenger_count") > 1)

    # 전체 통계, 승객수 필터 통계를 각각 agg().collect()로 따로 부르면 액션이 2번(Job 2개)
    # 생긴다. 두 agg() 결과(둘 다 1행짜리 DataFrame)를 unionByName으로 합쳐서 collect()를
    # 한 번만 호출하면 액션 1개로 줄어든다 (RDD 버전에서 count/sum/mean을 하나의 map+reduce로
    # 합친 것과 같은 방향의 최적화).
    total_stats = cleaned_df.agg(
        F.sum("fare_amount").alias("revenue"),
        F.sum("trip_distance").alias("distance"),
        F.count("*").alias("trips"),
    ).withColumn("group", F.lit("all"))

    multi_stats = multi_passenger_df.agg(
        F.sum("fare_amount").alias("revenue"),
        F.sum("trip_distance").alias("distance"),
        F.count("*").alias("trips"),
    ).withColumn("group", F.lit("multi_passenger"))

    stats_by_group = {row.group: row for row in total_stats.unionByName(multi_stats).collect()}

    fare_sum_total = stats_by_group["all"].revenue
    distance_sum_total = stats_by_group["all"].distance
    total_trips = stats_by_group["all"].trips

    multi_fare_sum_total = stats_by_group["multi_passenger"].revenue
    multi_distance_sum_total = stats_by_group["multi_passenger"].distance
    multi_total_trips = stats_by_group["multi_passenger"].trips
    print(f"Multi-passenger (passenger_count > 1) trips: {multi_total_trips}, revenue: {multi_fare_sum_total}, distance: {multi_distance_sum_total}")

    total_revenue = fare_sum_total
    avg_distance = distance_sum_total / total_trips

    reduce_start = time.time()

    daily_df = cleaned_df.groupBy("pickup_date").agg(
            F.count("*").alias("trip_count"),
            F.sum("fare_amount").alias("total_revenue"),
            F.avg("trip_distance").alias("avg_distance"),
    )
    
    daily_sorted = sorted(daily_df.collect())
    reduce_elapsed = time.time() - reduce_start
    print(f"DAILY_REDUCE_ELAPSED_SECONDS={reduce_elapsed:.3f}")

    print(f"Total trips: {total_trips}")
    print(f"Total revenue: {total_revenue}")
    print(f"Average trip distance: {avg_distance}")

    # 일별 트립 수 / 총수익도 화면에 표시
    print("Daily trip count / revenue:")
    for pickup_date, trip_count, daily_revenue, daily_avg_distance in daily_sorted:
        print(f"  {pickup_date}: trips={trip_count}, revenue={daily_revenue:.2f}, distance: {daily_avg_distance}")

    # daily_sorted는 이미 driver에 모아진 파이썬 리스트라 RDD로 다시 만들 필요 없이 바로 포맷팅
    daily_lines = [f"{pickup_date},{trip_count},{daily_revenue},{daily_avg_distance}" for pickup_date, trip_count, daily_revenue, daily_avg_distance in daily_sorted]
    write_single_csv(
        daily_lines,
        header="pickup_date,trip_count,total_revenue,avg_distance",
        final_csv_path=f"{output_dir}/daily_stats.csv",
    )

    summary_lines = [
        f"total_trips,{total_trips}",
        f"total_revenue,{total_revenue}",
        f"avg_distance,{avg_distance}",
    ]
    
    write_single_csv(
        summary_lines,
        header="metric,value",
        final_csv_path=f"{output_dir}/summary.csv",
    )

    # Join: 트립 데이터의 PULocationID를 taxi zone lookup 테이블(LocationID)과 조인해서
    # 자치구(Borough)별 트립 수/매출을 집계. lookup 테이블은 data/ 최상위가 아니라
    # data/lookup/에 따로 둬서 load_input_data의 *.csv glob에 걸리지 않게 함.
    zone_df = spark.read.schema(ZONE_SCHEMA).option("header", True) \
        .csv(f"{input_dir}/lookup/taxi_zone_lookup.csv")

    # 자치구는 많아야 십여 개인 작은 결과라, Spark 분산 정렬(orderBy, 셔플 필요)
    # 대신 daily_sorted와 같은 방식으로 collect() 후 파이썬 sorted()로 정렬한다.
    borough_df = cleaned_df.join(
        zone_df, cleaned_df.PULocationID == zone_df.LocationID, "left"
    ).groupBy("Borough").agg(
        F.count("*").alias("trip_count"),
        F.sum("fare_amount").alias("total_revenue"),
    )

    # borough_df가 아래 두 액션(collect, write)에서 재사용되므로 캐싱.
    # 캐싱 안 하면 join+groupBy가 두 번(collect용, write용) 실행된다.
    borough_df.cache()

    # Action 1 (Collect): driver로 모은 뒤 파이썬에서 트립 수 기준 내림차순 정렬
    borough_rows = sorted(borough_df.collect(), key=lambda row: row.trip_count, reverse=True)
    print("Borough-level trip count / revenue:")
    for row in borough_rows:
        print(f"  {row.Borough}: trips={row.trip_count}, revenue={row.total_revenue:.2f}")

    # Action 2 (Write): 파이썬 open()이 아니라 Spark의 DataFrameWriter로 직접 저장
    borough_df.coalesce(1).write.mode("overwrite").option("header", True) \
        .csv(f"{output_dir}/borough_stats")

    elapsed = time.time() - pipeline_start
    print(f"PIPELINE_ELAPSED_SECONDS={elapsed:.3f}")

    spark.stop()


if __name__ == "__main__":
    main()
