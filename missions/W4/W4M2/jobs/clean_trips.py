import sys
import glob

from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import IntegerType

if __name__ == "__main__":
    """
        사용법: spark-submit clean_trips.py [input_dir] [output_path]
        - input_dir: TLC 운행 기록 파일들이 있는 디렉터리 (기본값 /opt/data)
                     이름이 yellow_tripdata_*.parquet / yellow_tripdata_*.csv인 파일을 전부 찾아 합쳐서 읽음
                     (같은 폴더의 날씨 CSV 등 이름 패턴이 다른 파일은 무시함)
        - output_path: 정제된 결과를 Parquet으로 저장할 경로 (기본값 /opt/output/cleaned_trips)
    """
    spark = SparkSession \
        .builder \
        .appName("CleanTrips") \
        .getOrCreate()

    input_dir = sys.argv[1] if len(sys.argv) > 1 else "/opt/data"
    output_path = sys.argv[2] if len(sys.argv) > 2 else "/opt/output/cleaned_trips"

    # 요구사항: CSV/Parquet 등 다양한 파일 형식 처리
    # 파일명 패턴(yellow_tripdata_*)으로 걸러서, 같은 폴더의 날씨 CSV 같은 다른 종류 파일은 안 건드림
    parquet_paths = sorted(glob.glob(f"{input_dir}/yellow_tripdata_*.parquet"))
    csv_paths = sorted(glob.glob(f"{input_dir}/yellow_tripdata_*.csv"))

    dfs = []
    if parquet_paths:
        dfs.append(spark.read.parquet(*parquet_paths))
    if csv_paths:
        # CSV는 스키마가 없는 텍스트 포맷이라 inferSchema로 컬럼 타입을 추론해야
        # trip_distance 등 숫자 컬럼이 문자열이 아니라 숫자로 들어옴
        dfs.append(spark.read.option("header", True).option("inferSchema", True).csv(*csv_paths))

    if not dfs:
        raise FileNotFoundError(f"{input_dir}에 yellow_tripdata_*.parquet/csv 파일이 없습니다.")

    # 두 형식 모두 있으면 컬럼명 기준으로 합침 (컬럼 순서가 달라도 안전하게 union)
    df = dfs[0]
    for other in dfs[1:]:
        df = df.unionByName(other)

    raw_count = df.count()

    # 요구사항: 시간 필드를 표준 타임스탬프 형식으로 변환
    df = df \
        .withColumn("tpep_pickup_datetime", F.to_timestamp("tpep_pickup_datetime")) \
        .withColumn("tpep_dropoff_datetime", F.to_timestamp("tpep_dropoff_datetime"))

    # 이동 시간(분) 컬럼 추가 - 이후 평균 이동 시간 계산과 이상치 필터링에 사용
    df = df.withColumn(
        "trip_duration_minutes",
        (F.unix_timestamp("tpep_dropoff_datetime") - F.unix_timestamp("tpep_pickup_datetime")) / 60.0
    )

    # 요구사항: 결측값 처리 - passenger_count가 비어있는 행이 전체의 약 5% 존재
    # 이동시간/거리 지표에는 영향 없는 컬럼이라 버리지 않고 기본값(1명)으로 채움
    df = df.na.fill({"passenger_count": 1})
    df = df.withColumn("passenger_count", F.col("passenger_count").cast(IntegerType()))

    # 요구사항: 의미 없는 값(음수 이동 시간/거리) 필터링
    # 상한선도 함께 둔 이유: 실제 데이터에 하차 시각이 승차 시각보다 며칠 뒤이거나
    # trip_distance가 312,722마일처럼 말이 안 되는 이상치가 섞여 있어서, 그대로 두면 평균이 크게 왜곡됨
    # - 24시간: 뉴욕 시내 택시 운행이 하루를 넘기는 경우는 사실상 없다고 봄
    # - 100마일: 뉴욕에서 웬만한 인접 도시(필라델피아 등)까지의 거리도 100마일을 넘지 않음
    MAX_DURATION_MINUTES = 24 * 60
    MAX_DISTANCE_MILES = 100

    cleaned_df = df.filter(
        (F.col("trip_duration_minutes") > 0) & (F.col("trip_duration_minutes") <= MAX_DURATION_MINUTES) &
        (F.col("trip_distance") > 0) & (F.col("trip_distance") <= MAX_DISTANCE_MILES) &
        F.col("tpep_pickup_datetime").isNotNull() &
        F.col("tpep_dropoff_datetime").isNotNull()
    )

    cleaned_count = cleaned_df.count()

    # 요구사항: 결과가 사람이 읽기 쉬운 형식으로 저장/표시
    print(f"Raw records: {raw_count}")
    print(f"Cleaned records: {cleaned_count} ({cleaned_count / raw_count:.1%} kept)")

    cleaned_df.write.mode("overwrite").parquet(output_path)

    spark.stop()
