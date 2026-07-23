import sys
import random

from pyspark.sql import SparkSession, Row

if __name__ == "__main__":
    """
        사용법: spark-submit pi.py [input_path] [output_path]
        - input_path: 파티션 수 / 파티션당 샘플 수 설정이 담긴 입력 CSV 경로
                      (기본값 /opt/data/pi_config.csv)
        - output_path: 결과를 CSV로 저장할 경로 (기본값 /opt/output/pi_result)
    """
    spark = SparkSession \
        .builder \
        .appName("PythonPi") \
        .getOrCreate()

    input_path = sys.argv[1] if len(sys.argv) > 1 else "/opt/data/pi_config.csv"
    output_path = sys.argv[2] if len(sys.argv) > 2 else "/opt/output/pi_result"

    # 요구사항: 마운트된 볼륨(입력 경로)에서 데이터셋을 읽음
    # pi_config.csv에 partitions, samples_per_partition 컬럼이 들어있음
    config_df = spark.read.option("header", True).option("inferSchema", True).csv(input_path)
    config_row = config_df.first()
    partitions = config_row["partitions"]
    samples_per_partition = config_row["samples_per_partition"]

    # 파티션 하나당 샘플을 넉넉히 배정 - 파티션마다 실제로 처리할 데이터가 있어야
    # 결과를 저장할 때도 파티션 수만큼 의미 있는 파일이 생김
    n = samples_per_partition * partitions

    def count_hits_in_partition(partition_id, iterator):
        # PySpark 워커 프로세스는 fork로 뜨기 때문에 random 모듈이 부모와 같은 시드 상태를 물려받음
        # partition_id로 명시적으로 시드를 다르게 줘서 파티션마다 다른 난수 시퀀스가 나오게 함
        rng = random.Random(partition_id)
        hits = 0
        total = 0
        for _ in iterator:
            x = rng.random() * 2 - 1
            y = rng.random() * 2 - 1
            if x ** 2 + y ** 2 <= 1:
                hits += 1
            total += 1
        # 파티션별로 처리한 샘플 수와 원 안에 들어간 개수를 한 줄로 반환
        yield Row(partition_id=partition_id, num_samples=total, num_hits=hits)

    # 몬테카를로 방식의 파이 추정 로직 - mapPartitionsWithIndex로 파티션별 결과를 따로 집계
    partition_results = spark.sparkContext.parallelize(range(n), partitions) \
        .mapPartitionsWithIndex(count_hits_in_partition)

    result_df = spark.createDataFrame(partition_results)
    result_df.cache()

    total_hits = result_df.groupBy().sum("num_hits").collect()[0][0]
    pi_estimate = 4.0 * total_hits / n

    # 요구사항: 결과가 Spark 작업 로그에도 출력되어야 함
    print("Pi is roughly %f" % pi_estimate)

    # 요구사항: 결과를 지정된 출력 경로에 CSV로 저장
    # 파티션(=워커 수)만큼 실제 데이터가 담긴 파일이 나뉘어 저장됨 (coalesce 없이 그대로 저장)
    result_df.write.mode("overwrite").option("header", True).csv(output_path)

    spark.stop()
