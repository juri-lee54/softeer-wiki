import sys

import geopandas as gpd
import numpy as np
import pandas as pd

if __name__ == "__main__":
    """
        사용법: python3 prepare_road_network.py [lion_gdb_path] [zones_shapefile] [output_path]
        - lion_gdb_path: NYC DOT LION 도로망 File Geodatabase 경로
                         (기본값 /opt/data/lion_gdb/lion/lion.gdb, 레이어명 'lion')
        - zones_shapefile: TLC 택시존 경계 shapefile 경로 (기본값 /opt/data/taxi_zones/taxi_zones.shp)
        - output_path: 존별 도로망 집계 결과를 저장할 CSV 경로 (기본값 /opt/data/zone_road_suitability.csv)

        "로보택시 신규 서비스 지역 우선순위 스코어카드"의 2층(AV 운행 적합도) 잡.
        도로 중심선 하나하나(도로폭/차선수/일방통행 여부)를 택시존에 공간조인해서
        존별로 집계한다 - 좁고 일방통행이 많은 동네(West Village 등)와 넓은 애비뉴
        중심 동네(Midtown 등)가 이 지표로 구분되는지 확인하는 게 목적.

        주의: 이 스크립트는 spark-submit이 아니라 python3로 직접 실행한다.
        예) docker exec spark-master python3 /opt/jobs/prepare_road_network.py
        이유: prepare_crime_data.py와 동일 - 결과가 존 단위(263개)로 항상 작아서
        Spark 분산 처리 없이 geopandas 한 번으로 충분하다.
    """
    lion_gdb_path = sys.argv[1] if len(sys.argv) > 1 else "/opt/data/lion_gdb/lion/lion.gdb"
    zones_shapefile = sys.argv[2] if len(sys.argv) > 2 else "/opt/data/taxi_zones/taxi_zones.shp"
    output_path = sys.argv[3] if len(sys.argv) > 3 else "/opt/data/zone_road_suitability.csv"

    # 존별 도로 표본이 이보다 적으면 평균값이 몇 개 세그먼트에 좌우돼 불안정해서 판단을 보류함
    # (demand_gap.py의 MIN_TRIPS_PER_BUCKET과 같은 이유 - 소표본 왜곡 방지)
    MIN_ROAD_SEGMENTS = 15

    roads = gpd.read_file(lion_gdb_path, layer="lion")

    # LION의 RW_TYPE/Number_Travel_Lanes는 고정폭 문자열이라 " 1"처럼 앞에 공백이 붙어 있어 strip 필요
    rw_type = roads["RW_TYPE"].astype(str).str.strip()
    status = roads["Status"].astype(str).str.strip()
    traf_dir = roads["TrafDir"].astype(str).str.strip()

    # 실제 차량이 다니는 일반 도로만 남김: RW_TYPE=1(일반 도로, 고속도로/다리/터널/보행로/사도 등 제외),
    # Status=2(현재 유효한 도로, 폐도로/계획도로 등 제외), TrafDir이 T/W/A 중 하나(방향 정보 없는 세그먼트 제외)
    is_drivable_street = (rw_type == "1") & (status == "2") & traf_dir.isin(["T", "W", "A"])
    roads = roads[is_drivable_street].copy()

    roads["travel_lanes"] = pd.to_numeric(
        roads["Number_Travel_Lanes"].astype(str).str.strip(), errors="coerce"
    )
    roads["is_one_way"] = traf_dir[is_drivable_street].isin(["W", "A"])

    zones_gdf = gpd.read_file(zones_shapefile)[["LocationID", "geometry"]]
    if roads.crs != zones_gdf.crs:
        roads = roads.to_crs(zones_gdf.crs)

    # 도로는 선(line)이라 폴리곤과 겹치는 면적 대신, 세그먼트 중점(centroid)이 어느 존에 속하는지로 판단
    roads_points = roads.copy()
    roads_points["geometry"] = roads.geometry.centroid

    joined = gpd.sjoin(roads_points, zones_gdf, how="inner", predicate="within")

    zone_roads = joined.groupby("LocationID").agg(
        segment_count=("is_one_way", "size"),
        one_way_segment_count=("is_one_way", "sum"),
        avg_street_width_ft=("StreetWidth_Min", "mean"),
        avg_travel_lanes=("travel_lanes", "mean"),
    ).reset_index()

    # 신고 0건인 존도 남겨야 했던 prepare_crime_data.py와 같은 이유로, 도로가 없는 존(주로 수역/공원)도 남김
    all_zones = zones_gdf[["LocationID"]].drop_duplicates("LocationID")
    zone_roads = all_zones.merge(zone_roads, on="LocationID", how="left").fillna(
        {"segment_count": 0, "one_way_segment_count": 0}
    )

    zone_roads["one_way_ratio"] = (
        zone_roads["one_way_segment_count"] / zone_roads["segment_count"].replace(0, np.nan)
    ).round(3)
    zone_roads["avg_street_width_ft"] = zone_roads["avg_street_width_ft"].round(1)
    zone_roads["avg_travel_lanes"] = zone_roads["avg_travel_lanes"].round(2)

    zone_roads["has_enough_road_data"] = zone_roads["segment_count"] >= MIN_ROAD_SEGMENTS
    zone_roads = zone_roads.drop(columns=["one_way_segment_count"]).sort_values(
        "segment_count", ascending=False
    )

    excluded = int((~zone_roads["has_enough_road_data"]).sum())

    # 요구사항: 결과가 사람이 읽기 쉬운 형식으로 표시 - 표본 부족분을 숨기지 않고 명시
    print(f"공간조인된 도로 세그먼트: {len(joined):,} / 필터링 후 전체 {len(roads):,}개 중")
    print(f"전체 {len(zone_roads)}개 존 중 도로 표본 부족(세그먼트 {MIN_ROAD_SEGMENTS}개 미만)으로 판단 보류: {excluded}개")
    print("도로폭이 가장 넓은 존 상위 10개:")
    print(zone_roads[zone_roads["has_enough_road_data"]].sort_values(
        "avg_street_width_ft", ascending=False
    ).head(10).to_string(index=False))
    print("\n일방통행 비율이 가장 높은 존 상위 10개:")
    print(zone_roads[zone_roads["has_enough_road_data"]].sort_values(
        "one_way_ratio", ascending=False
    ).head(10).to_string(index=False))

    zone_roads.to_csv(output_path, index=False)
    print(f"\n저장 완료: {output_path}")
