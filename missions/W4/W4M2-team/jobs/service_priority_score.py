import sys

import numpy as np

from pyspark.sql import SparkSession

if __name__ == "__main__":
    """
        사용법: spark-submit service_priority_score.py [demand_gap_path] [road_path] [zone_lookup_path] [output_path]
        - demand_gap_path: demand_gap.py 결과 (기본값 /opt/output/demand_gap)
        - road_path: prepare_road_network.py가 만든 존별 도로망 집계 CSV (기본값 /opt/data/zone_road_suitability.csv)
        - zone_lookup_path: TLC 공개 존 이름/자치구 매핑 CSV (기본값 /opt/data/taxi_zone_lookup.csv)
        - output_path: 최종 우선순위 스코어카드 CSV (기본값 /opt/output/service_priority_score)

        "뉴욕시 로보택시 신규 서비스 지역 우선순위 스코어카드"의 최종 결합 잡.
        1층(수요 공백: night_day_gap_ratio)과 2층(AV 도로 적합도: 도로폭/차선수/일방통행)을
        존 단위로 합쳐서 "수요는 있는데 서비스가 약하고, 동시에 도로 구조상 AV가 다니기에도
        무리 없는 구역"의 순위를 매긴다.

        일방통행 비율에 대한 주의: 실제로 돌려보니 미드타운 애비뉴처럼 넓고 차선 많은 구역도
        일방통행 비율이 높게 나온다(뉴욕 도로망 자체가 애비뉴 단위로 일방통행이라서). 그래서
        일방통행 비율 하나만으로는 "복잡한 동네"를 가려내지 못하고, 실제로 West Village류를
        가려내는 건 도로폭/차선수 쪽이었다 - 그래서 일방통행 비율의 가중치를 더 낮게 둠.
    """
    spark = SparkSession \
        .builder \
        .appName("ServicePriorityScore") \
        .getOrCreate()

    demand_gap_path = sys.argv[1] if len(sys.argv) > 1 else "/opt/output/demand_gap"
    road_path = sys.argv[2] if len(sys.argv) > 2 else "/opt/data/zone_road_suitability.csv"
    zone_lookup_path = sys.argv[3] if len(sys.argv) > 3 else "/opt/data/taxi_zone_lookup.csv"
    output_path = sys.argv[4] if len(sys.argv) > 4 else "/opt/output/service_priority_score"

    # 세 지표를 합칠 때 쓰는 가중치 - 일방통행 비율은 위 이유로 절반만 반영
    WEIGHTS = {"demand_gap": 1.0, "width": 1.0, "lanes": 1.0, "one_way": 0.5}

    demand_df = spark.read.option("header", True).option("inferSchema", True).csv(demand_gap_path).toPandas()
    road_df = spark.read.option("header", True).option("inferSchema", True).csv(road_path).toPandas()
    zone_lookup_df = spark.read.option("header", True).option("inferSchema", True).csv(zone_lookup_path).toPandas()

    merged = demand_df.merge(road_df, on="LocationID", how="inner") \
        .merge(zone_lookup_df, on="LocationID", how="left")

    # 두 층 중 하나라도 표본 부족으로 판단 보류된 존은 순위 대상에서 제외 - 조용히 버리지 않고 개수를 로그로 남김
    merged["has_enough_data"] = merged["has_enough_data"].astype(bool) & merged["has_enough_road_data"].astype(bool)
    scorable = merged[merged["has_enough_data"]].copy()
    excluded = len(merged) - len(scorable)

    def zscore(series):
        return (series - series.mean()) / series.std(ddof=0)

    scorable["demand_gap_z"] = zscore(scorable["night_day_gap_ratio"])
    scorable["width_z"] = zscore(scorable["avg_street_width_ft"])
    scorable["lanes_z"] = zscore(scorable["avg_travel_lanes"])
    # 일방통행 비율이 높을수록(폭/차선과 독립적으로) 회전·합류가 잦아진다고 보고 소폭 감점
    scorable["one_way_z"] = zscore(scorable["one_way_ratio"])

    scorable["road_suitability_score"] = (
        WEIGHTS["width"] * scorable["width_z"] +
        WEIGHTS["lanes"] * scorable["lanes_z"] -
        WEIGHTS["one_way"] * scorable["one_way_z"]
    )
    # road_suitability_score는 z-score 두 개를 더한 값이라 그대로 더하면 값 범위가
    # demand_gap_z(z-score 1개)보다 훨씬 커져서 최종 점수가 도로 적합도에 쏠린다.
    # 두 층의 영향력이 비슷해지도록 다시 z-score로 정규화한 뒤 합침
    scorable["road_suitability_z"] = zscore(scorable["road_suitability_score"])
    scorable["final_priority_score"] = (
        WEIGHTS["demand_gap"] * scorable["demand_gap_z"] + scorable["road_suitability_z"]
    )

    result = scorable.sort_values("final_priority_score", ascending=False).reset_index(drop=True)
    result["priority_rank"] = result.index + 1

    output_cols = [
        "priority_rank", "LocationID", "Zone", "Borough", "final_priority_score",
        "night_day_gap_ratio", "day_trip_count", "night_trip_count",
        "avg_street_width_ft", "avg_travel_lanes", "one_way_ratio",
        "demand_gap_z", "road_suitability_z"
    ]
    result_out = result[[c for c in output_cols if c in result.columns]]

    # 요구사항: 결과가 사람이 읽기 쉬운 형식으로 표시 - 제외된 존 개수를 숨기지 않음
    print(f"전체 {len(merged)}개 존 중 표본 부족(수요 또는 도로망 데이터)으로 순위 대상에서 제외: {excluded}개")
    print("\n신규 서비스 우선순위 상위 20개 존:")
    print(result_out.head(20).to_string(index=False))

    spark.createDataFrame(result_out).coalesce(1).write.mode("overwrite").option("header", True).csv(output_path)

    spark.stop()
