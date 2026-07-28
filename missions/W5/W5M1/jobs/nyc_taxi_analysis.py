import sys
import time
from collections import namedtuple
from datetime import datetime

from pyspark.sql import SparkSession
import glob


# 한 건의 행을 표현. parquet/csv 파싱 결과를 이 형태로 통일
TripRecord = namedtuple(
    "TripRecord",
    ["pickup_dt", "dropoff_dt", "passenger_count", "trip_distance", "fare_amount", "duration_min", "pickup_date"],
)

MAX_DURATION_MINUTES = 24 * 60
MAX_DISTANCE_MILES = 100
# 이번에 분석하는 파일들이 2024년 데이터라 그 해를 기준으로 상한, 하한을 둠
MIN_PICKUP_YEAR = 2020
MAX_PICKUP_YEAR = 2024


def parse_parquet_row(row):
    """
    spark.read.parquet(...).rdd 로 얻은 Row 객체 한 개를 TripRecord로 변환한다.
    파싱에 실패하거나 필수 필드가 없으면 None을 반환한다.
    """
    try:
        pickup_dt = row.tpep_pickup_datetime
        dropoff_dt = row.tpep_dropoff_datetime

        # 결측치 제거
        if pickup_dt is None or dropoff_dt is None:
            return None

        trip_distance = row.trip_distance
        fare_amount = row.fare_amount
        if trip_distance is None or fare_amount is None:
            return None

        # passenger_count는 None 또는 0으로 결측이 표시되는 걸 확인
        # 둘 다 결측으로 보고 기본값 1로 채움. 
        passenger_count = row.passenger_count
        if passenger_count is None or passenger_count == 0:
            passenger_count = 1

        # parquet의 datetime끼리 뺄셈하면 timedelta가 나오므로 분 단위로 환산
        duration_min = (dropoff_dt - pickup_dt).total_seconds() / 60.0

        # 날짜별 집계(reduceByKey)에서 key로 쓸 문자열. strftime은 datetime -> 문자열 변환
        pickup_date = pickup_dt.strftime("%Y-%m-%d")

        return TripRecord(
            pickup_dt=pickup_dt,
            dropoff_dt=dropoff_dt,
            passenger_count=int(passenger_count),
            trip_distance=float(trip_distance),
            fare_amount=float(fare_amount),
            duration_min=duration_min,
            pickup_date=pickup_date,
        )
    except (AttributeError, TypeError, ValueError):
        # Row에 필요한 컬럼이 없거나 타입 캐스팅이 실패하면 이 행은 버림
        return None


def parse_csv_line(line):
    """
    sc.textFile(...) 로 읽은 CSV 한 줄(문자열)을 TripRecord로 변환한다.
    헤더 줄이거나 파싱에 실패하면 None을 반환한다.
    """
    try:
        fields = line.split(",")
        if len(fields) < 11:
            return None

        # 헤더 줄(또는 깨진 줄) 판별: VendorID 자리가 정수로 파싱 안 되면 데이터 행이 아니라고 보고 버림
        try:
            int(fields[0])
        except ValueError:
            return None

        pickup_dt = datetime.strptime(fields[1], "%Y-%m-%d %H:%M:%S")
        dropoff_dt = datetime.strptime(fields[2], "%Y-%m-%d %H:%M:%S")

        trip_distance = float(fields[4])
        fare_amount = float(fields[10])

        # passenger_count는 parquet과 동일하게 0/빈값을 결측으로 보고 기본값 1로 채움
        passenger_count_raw = fields[3].strip()
        passenger_count = int(float(passenger_count_raw)) if passenger_count_raw else 0
        if passenger_count == 0:
            passenger_count = 1

        duration_min = (dropoff_dt - pickup_dt).total_seconds() / 60.0
        pickup_date = pickup_dt.strftime("%Y-%m-%d")

        return TripRecord(
            pickup_dt=pickup_dt,
            dropoff_dt=dropoff_dt,
            passenger_count=passenger_count,
            trip_distance=trip_distance,
            fare_amount=fare_amount,
            duration_min=duration_min,
            pickup_date=pickup_date,
        )
    except (ValueError, IndexError):
        # 콤마 개수가 안 맞거나 숫자/날짜 형식이 깨진 행은 버림
        return None


def is_valid(record):
    """
    이상치를 걸러내는 조건. True면 유지, False면 제거 대상.
    """
    if (0 < record.duration_min <= MAX_DURATION_MINUTES) and (0 < record.trip_distance <= MAX_DISTANCE_MILES) \
        and (record.fare_amount > 0) and (record.pickup_dt is not None) and (record.dropoff_dt is not None) \
        and (MIN_PICKUP_YEAR <= record.pickup_dt.year <= MAX_PICKUP_YEAR):
        return True
    return False
        

def to_daily_kv(record):
    """
    reduceByKey에 넘길 (key, value) 튜플로 변환.
    key: pickup_date, value: (fare_amount, trip_distance, 1건)
    """
    
    return (record.pickup_date, (record.fare_amount, record.trip_distance, 1)) 
    

def sum_daily_kv(a, b):
    """
    reduceByKey에서 같은 날짜의 두 값을 합치는 함수. (fare합, distance합, count합)
    """
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def load_input_rdd(sc, spark, input_dir):
    """
    input_dir 안의 parquet/csv 파일을 모두 읽어 RDD[TripRecord] 하나로 합쳐 반환한다.
    """
    parquet_path = glob.glob(f"{input_dir}/*.parquet")
    csv_path = glob.glob(f"{input_dir}/*.csv")

    if len(parquet_path) == 0 and len(csv_path) == 0:
        raise FileNotFoundError(f"{input_dir}에 parquet/csv 파일이 없습니다.")

    if len(parquet_path) > 0:
        pq_rdd = spark.read.parquet(*parquet_path).rdd
        pq_rdd = pq_rdd.map(parse_parquet_row)

    if len(csv_path) > 0:
        csv_rdd = sc.textFile(",".join(csv_path))
        csv_rdd = csv_rdd.map(parse_csv_line)

    if len(parquet_path) > 0 and len(csv_path) > 0:
        raw_rdd = pq_rdd.union(csv_rdd)
        return raw_rdd
    elif len(parquet_path) > 0:
        return pq_rdd
    else:
        return csv_rdd
    

def write_single_csv(lines, header, final_csv_path):
    """
    이미 driver로 모아진(파이썬 리스트) 줄들을 헤더가 붙은 단일 .csv 파일로 저장한다.
    RDD를 여기서 collect()하지 않는다 — 호출하는 쪽에서 이미 collect()해서 얻은 결과를
    재사용해야 불필요한 Job이 추가로 생기지 않는다.
    """
    with open(final_csv_path, "w") as f:
        f.write(header + "\n")
        for line in lines:
            f.write(line + "\n")


def main():
    input_dir = sys.argv[1] if len(sys.argv) > 1 else "/opt/data"
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "/opt/output"

    spark = SparkSession.builder.appName("taxiAnalysis").getOrCreate()
    sc = spark.sparkContext

    raw_rdd = load_input_rdd(sc, spark, input_dir)

    ##  RDD transformation 
    # 1) 파싱 실패 행 제거
    parsed_rdd = raw_rdd.filter(lambda x: x is not None)

    # 2) 이상치/결측 제거
    cleaned_rdd = parsed_rdd.filter(is_valid)

    # cleaned_rdd는 아래 여러 액션(count, sum, mean, reduceByKey)에서 재사용되므로 캐싱
    cleaned_rdd.cache()

    pipeline_start = time.time()

    # 3) 총 트립 수, 총 매출, 평균 거리
    # count/sum/mean을 각각 따로 호출하면 액션 3번 = Job 3개가 생김.
    # 하나의 map + reduce로 합쳐서 Job 1개로 줄임 (fare합, distance합, count를 한 번에 집계)
    fare_sum_total, distance_sum_total, total_trips = cleaned_rdd.map(
        lambda r: (r.fare_amount, r.trip_distance, 1)
    ).reduce(lambda a, b: (a[0] + b[0], a[1] + b[1], a[2] + b[2]))
    total_revenue = fare_sum_total
    avg_distance = distance_sum_total / total_trips

    # 4) 날짜별 key-value로 변환
    # 5) reduceByKey로 날짜별 (매출합, 거리합, 트립수) 집계
    reduce_start = time.time()
    daily_rdd = cleaned_rdd.map(to_daily_kv).reduceByKey(sum_daily_kv)
    # 날짜가 93개뿐인 작은 결과라 RDD 차원의 분산 정렬(sortByKey)은 오히려 낭비 -
    # (경계 샘플링 Job + 셔플 정렬 Job이 추가로 생김) collect() 후 파이썬 sorted()로 정렬
    daily_sorted = sorted(daily_rdd.collect())  # 여기서 실제로 reduceByKey 셔플이 실행됨
    reduce_elapsed = time.time() - reduce_start
    print(f"DAILY_REDUCE_ELAPSED_SECONDS={reduce_elapsed:.3f}")

    print(f"Total trips: {total_trips}")
    print(f"Total revenue: {total_revenue}")
    print(f"Average trip distance: {avg_distance}")

    # 일별 트립 수 / 총수익도 화면에 표시
    print("Daily trip count / revenue:")
    for pickup_date, (fare_sum, distance_sum, count) in daily_sorted:
        print(f"  {pickup_date}: trips={count}, revenue={fare_sum:.2f}")

    # daily_sorted는 이미 driver에 모아진 파이썬 리스트라 RDD로 다시 만들 필요 없이 바로 포맷팅
    daily_lines = [f"{pickup_date},{count},{fare_sum}" for pickup_date, (fare_sum, distance_sum, count) in daily_sorted]
    write_single_csv(
        daily_lines,
        header="pickup_date,trip_count,total_revenue",
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

    elapsed = time.time() - pipeline_start
    print(f"PIPELINE_ELAPSED_SECONDS={elapsed:.3f}")

    spark.stop()


if __name__ == "__main__":
    main()
