"""
etl_project_gdp.py 와 동일한 Extract/Transform 로직을 사용하되,
결과를 JSON뿐 아니라 SQLite 데이터베이스(World_Economies.db)의
Countries_by_GDP 테이블에도 적재하고, 화면 출력은 SQL 쿼리

ETL 단계
    1) Extract   : Wikipedia GDP 테이블을 BeautifulSoup으로 파싱
    2) Transform : GDP 단위를 Billion USD로 변환(소수점 2자리), GDP 내림차순 정렬
    3) Load      : Countries_by_GDP.json 저장 + World_Economies.db 의
                   Countries_by_GDP 테이블에 저장
"""

import os
import sqlite3
from datetime import datetime

import pandas as pd
import requests
from bs4 import BeautifulSoup

# --- 설정값 ---
URL = "https://en.wikipedia.org/wiki/List_of_countries_by_GDP_(nominal)"
LOG_PATH = "./missions/w1/logs/etl_project_log.txt"
DB_NAME = "./missions/w1/data/World_Economies.db"
TABLE_NAME = "Countries_by_GDP"
TABLE_ATTRIBS = ["Country", "Region", "GDP_USD_billion"]
GDP_THRESHOLD_BILLION = 100
TOP_N_PER_REGION = 5


# --- 로그 기록 함수 ---
def log_progress(message: str) -> None:
    """
    ETL 진행 상황을 etl_project_log.txt 파일에 append 방식으로 기록한다.
    시간 포맷: Year-Monthname-Day-Hour-Minute-Second
    """
    timestamp_format = "%Y-%B-%d-%H-%M-%S"
    timestamp = datetime.now().strftime(timestamp_format)

    # LOG_PATH에 디렉토리 경로가 포함된 경우, 없으면 미리 생성
    log_dir = os.path.dirname(LOG_PATH)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)

    with open(LOG_PATH, "a", encoding="utf-8") as log_file:
        log_file.write(f"{timestamp}, {message}\n")


# --- Extract ---
def extract(url: str) -> pd.DataFrame:
    """Wikipedia GDP 페이지를 스크래핑하여 Country, Region, GDP_USD_millions DataFrame 반환."""
    log_progress("Extract 단계 시작")

    headers = {"User-Agent": "Mozilla/5.0 (ETL Project)"}
    response = requests.get(url, headers=headers)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    tables = soup.find_all("table", {"class": "wikitable"})
    target_table = None
    for table in tables:
        header_text = table.find("tr").get_text()
        if "Country" in header_text and "IMF" in header_text:
            target_table = table
            break

    if target_table is None:
        raise ValueError("GDP 데이터 테이블을 찾을 수 없습니다. 페이지 구조를 확인하세요.")

    countries, regions, gdp_values = [], [], []

    for row in target_table.find_all("tr"):
        cols = row.find_all("td")
        if len(cols) < 3:
            continue

        country_idx = None
        for i, col in enumerate(cols):
            if col.find("a") is not None:
                country_idx = i
                break

        if country_idx is None:
            continue

        country = cols[country_idx].get_text(strip=True)
        if country in ("World",):
            continue

        if country_idx + 2 >= len(cols):
            continue

        region = cols[country_idx + 1].get_text(strip=True)
        gdp_text = cols[country_idx + 2].get_text(strip=True)
        gdp_text = gdp_text.replace(",", "").replace("—", "").strip()

        if not gdp_text or not gdp_text.replace(".", "", 1).isdigit():
            continue

        countries.append(country)
        regions.append(region)
        gdp_values.append(float(gdp_text))

    df = pd.DataFrame(
        {"Country": countries, "Region": regions, "GDP_USD_millions": gdp_values}
    )

    log_progress(f"Extract 단계 종료 (총 {len(df)}개 국가 수집)")
    return df


# --- Transform ---
def transform(df: pd.DataFrame) -> pd.DataFrame:
    """GDP 단위를 Billion USD(소수점 2자리)로 변환하고 내림차순 정렬."""
    log_progress("Transform 단계 시작")

    df = df.copy()
    df["GDP_USD_billion"] = (df["GDP_USD_millions"] / 1000).round(2)
    df = df.drop(columns=["GDP_USD_millions"])
    df = df.sort_values(by="GDP_USD_billion", ascending=False).reset_index(drop=True)

    log_progress("Transform 단계 종료")
    return df[TABLE_ATTRIBS]


# --- Load --- 
def load_to_db(df: pd.DataFrame, db_name: str, table_name: str) -> None:
    """
    가공된 DataFrame을 SQLite DB에 저장한다.
    매번 실행 시 최신 데이터로 테이블을 교체(replace)한다.
    """
    log_progress("DB Load 단계 시작")
    
    # db_name에 디렉토리 경로가 포함된 경우, 없으면 미리 생성
    db_dir = os.path.dirname(db_name)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    conn = sqlite3.connect(db_name)
    try:
        df.to_sql(table_name, conn, if_exists="replace", index=False)
    finally:
        conn.close()

    log_progress(f"DB Load 단계 종료 ({db_name} / {table_name} 테이블 저장 완료)")


# ---화면 출력 ---
def run_query_above_threshold(db_name: str, table_name: str, threshold: float) -> None:
    """SQL 쿼리로 GDP가 threshold(Billion USD) 이상인 국가를 조회하여 출력한다."""
    log_progress(f"SQL 쿼리 실행: GDP {threshold}B 이상 국가")

    conn = sqlite3.connect(db_name)
    try:
        query = f"""
            SELECT Country, Region, GDP_USD_billion
            FROM {table_name}
            WHERE GDP_USD_billion >= {threshold}
            ORDER BY GDP_USD_billion DESC
        """
        result = pd.read_sql_query(query, conn)
    finally:
        conn.close()

    print(f"\n=== [SQL] GDP {threshold}B USD 이상 국가 ({len(result)}개) ===")
    print(result.to_string(index=False))

    log_progress("SQL 쿼리 종료: GDP 100B 이상 국가")


def run_query_region_top5_average(db_name: str, table_name: str, top_n: int) -> None:
    """
    SQL 쿼리로 Region별 상위 top_n개 국가의 GDP 평균을 조회하여 출력한다.
    SQLite는 표준 window function(RANK)을 지원하므로 이를 활용한다.
    """
    log_progress(f"SQL 쿼리 실행: Region별 top{top_n} GDP 평균")

    conn = sqlite3.connect(db_name)
    try:
        query = f"""
            WITH ranked AS (
                SELECT
                    Region,
                    GDP_USD_billion,
                    RANK() OVER (
                        PARTITION BY Region ORDER BY GDP_USD_billion DESC
                    ) AS rnk
                FROM {table_name}
            )
            SELECT
                Region,
                ROUND(AVG(GDP_USD_billion), 2) AS avg_top{top_n}_gdp_billion
            FROM ranked
            WHERE rnk <= {top_n}
            GROUP BY Region
            ORDER BY avg_top{top_n}_gdp_billion DESC
        """
        result = pd.read_sql_query(query, conn)
    finally:
        conn.close()

    print(f"\n=== [SQL] Region별 Top {top_n} 국가 GDP 평균 (Billion USD) ===")
    print(result.to_string(index=False))

    log_progress(f"SQL 쿼리 종료: Region별 top{top_n} GDP 평균")


# --- 메인 실행부 ---
def main() -> None:
    log_progress("=== ETL(with SQL) 프로세스 시작 ===")

    raw_df = extract(URL)
    transformed_df = transform(raw_df)

    load_to_db(transformed_df, DB_NAME, TABLE_NAME)

    run_query_above_threshold(DB_NAME, TABLE_NAME, GDP_THRESHOLD_BILLION)
    run_query_region_top5_average(DB_NAME, TABLE_NAME, TOP_N_PER_REGION)

    log_progress("=== ETL(with SQL) 프로세스 종료 ===\n")


if __name__ == "__main__":
    main()