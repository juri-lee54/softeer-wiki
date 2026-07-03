"""
국가별 GDP(IMF 명목 GDP 추정치) 데이터를 Wikipedia에서 스크래핑하여
가공한 뒤 JSON 파일로 저장하는 ETL 파이프라인.

ETL 단계
    1) Extract : Wikipedia 페이지의 GDP 테이블을 BeautifulSoup으로 파싱
    2) Transform : GDP 단위를 Billion USD로 변환(소수점 2자리), GDP 내림차순 정렬
    3) Load : 결과를 Countries_by_GDP.json 으로 저장
"""

import json
from datetime import datetime

import pandas as pd
import requests
from bs4 import BeautifulSoup
import os

# --- 설정값 ---
URL = "https://en.wikipedia.org/wiki/List_of_countries_by_GDP_(nominal)"
JSON_PATH = "./missions/w1/data/Countries_by_GDP.json"
LOG_PATH = "./missions/w1/logs/etl_project_log.txt"
TABLE_ATTRIBS = ["Country", "Region", "GDP_USD_billion"]
GDP_THRESHOLD_BILLION = 100  # 화면 출력 시 필터링 기준
TOP_N_PER_REGION = 5         # Region별 top N 국가


# --- 로그 기록 함수 ---
def log_progress(message: str) -> None:
    """
    ETL 진행 상황을 etl_project_log.txt 파일에 append 방식으로 기록한다.
    시간 포맷: Year-Monthname-Day-Hour-Minute-Second (예: 2026-July-02-14-30-05)
    로그 포맷: "시간, 메시지"
    """
    timestamp_format = "%Y-%B-%d-%H-%M-%S"  #'Year-Monthname-Day-Hour-Minute-Second'
    timestamp = datetime.now().strftime(timestamp_format)
    
    # LOG_PATH에 디렉토리 경로가 포함된 경우, 없으면 미리 생성
    log_dir = os.path.dirname(LOG_PATH)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)


    with open(LOG_PATH, "a", encoding="utf-8") as log_file:
        log_file.write(f"{timestamp}, {message}\n")


# --- Extract ---
def extract(url: str) -> pd.DataFrame:
    """
    Wikipedia GDP 페이지를 스크래핑하여 국가(Country), 지역(Region),
    IMF 추정 GDP(백만 달러, GDP_USD_millions)를 담은 DataFrame을 반환한다.
    """
    log_progress("Extract 단계 시작")

    headers = {"User-Agent": "Mozilla/5.0 (ETL Project)"}
    response = requests.get(url, headers=headers)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    # 여러 개의 wikitable 중에서 'IMF' 와 'Country/Territory' 를
    # 헤더에 포함하는 테이블을 GDP 데이터 테이블로 식별한다.
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
            continue  # 헤더 행 등은 건너뜀

        # 국가명이 들어있는 셀은 <a> 태그를 포함하는 첫 번째 td.
        # (앞에 순위(rank) td가 있을 수도, 없을 수도 있어 위치 대신 링크로 식별)
        country_idx = None
        for i, col in enumerate(cols):
            if col.find("a") is not None:
                country_idx = i
                break

        if country_idx is None:
            continue

        country = cols[country_idx].get_text(strip=True)

        # World(전세계 합계) 행은 국가가 아니므로 제외
        if country in ("World",):
            continue

        # 국가 다음 컬럼 = Region, 그 다음 컬럼 = IMF Estimate(GDP, 백만 달러)
        if country_idx + 2 >= len(cols):
            continue

        region = cols[country_idx + 1].get_text(strip=True)
        gdp_text = cols[country_idx + 2].get_text(strip=True)
        gdp_text = gdp_text.replace(",", "").replace("—", "").strip()

        # 숫자가 아닌 값(추정치 없음 등)은 건너뜀
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
    """
    GDP 단위를 백만(million) USD -> 십억(billion) USD 로 변환하고
    소수점 2자리로 반올림한다. GDP 내림차순으로 정렬한다.
    """
    log_progress("Transform 단계 시작")

    df = df.copy()
    df["GDP_USD_billion"] = (df["GDP_USD_millions"] / 1000).round(2)
    df = df.drop(columns=["GDP_USD_millions"])
    df = df.sort_values(by="GDP_USD_billion", ascending=False).reset_index(drop=True)

    log_progress("Transform 단계 종료")
    return df[TABLE_ATTRIBS]


# --- Load ---
def load_to_json(df: pd.DataFrame, path: str) -> None:
    """가공된 DataFrame을 JSON 파일로 저장한다."""
    log_progress("Load 단계 시작")
 
    # path에 디렉토리 경로가 포함된 경우, 없으면 미리 생성
    json_dir = os.path.dirname(path)
    if json_dir:
        os.makedirs(json_dir, exist_ok=True)
 
    df.to_json(path, orient="records", indent=2, force_ascii=False)
    log_progress(f"Load 단계 종료 ({path} 저장 완료)")


# --- 화면 출력 ---
def print_countries_above_threshold(df: pd.DataFrame, threshold: float) -> None:
    """GDP가 threshold(Billion USD) 이상인 국가만 화면에 출력한다."""
    log_progress(f"GDP {threshold}B 이상 국가 조회 시작")
    result = df[df["GDP_USD_billion"] >= threshold]

    print(f"\n=== GDP {threshold}B USD 이상 국가 ({len(result)}개) ===")
    print(result.to_string(index=False))

    log_progress("GDP 100B 이상 국가 조회 종료")


def print_region_top5_average(df: pd.DataFrame, top_n: int) -> None:
    """Region별 상위 top_n개 국가의 GDP 평균을 화면에 출력한다."""
    log_progress("Region별 top5 GDP 평균 계산 시작")

    # Region 내에서 GDP 내림차순으로 순위를 매긴 뒤 상위 top_n개만 선택
    sorted_df = df.sort_values(["Region", "GDP_USD_billion"], ascending=[True, False]).copy()
    sorted_df["rank_in_region"] = sorted_df.groupby("Region").cumcount() + 1
    top_n_df = sorted_df[sorted_df["rank_in_region"] <= top_n]

    region_avg = (
        top_n_df.groupby("Region")["GDP_USD_billion"]
        .mean()
        .round(2)
        .sort_values(ascending=False)
    )

    print(f"\n=== Region별 Top {top_n} 국가 GDP 평균 (Billion USD) ===")
    print(region_avg.to_string())

    log_progress("Region별 top5 GDP 평균 계산 종료")


# --- 메인 ---
def main() -> None:
    log_progress("=== ETL 프로세스 시작 ===")

    raw_df = extract(URL)
    transformed_df = transform(raw_df)
    load_to_json(transformed_df, JSON_PATH)

    print_countries_above_threshold(transformed_df, GDP_THRESHOLD_BILLION)
    print_region_top5_average(transformed_df, TOP_N_PER_REGION)

    log_progress("=== ETL 프로세스 종료 ===\n")


if __name__ == "__main__":
    main()