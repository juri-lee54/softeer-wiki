#!/bin/bash
# NYC TLC 운행 기록(Parquet)과 NOAA 기상 데이터(CSV)를 data/ 폴더에 받는 스크립트
# 사용법: ./download_data.sh [start_month] [end_month]
#   start_month, end_month: YYYY-MM 형식 (기본값 2024-01 ~ 2024-06)
#
# 예:
#   ./download_data.sh                     # 기본값(2024-01~2024-06) 다운로드
#   ./download_data.sh 2024-01 2024-06
#   ./download_data.sh 2023-11 2024-02      # 연도가 걸쳐 있어도 됨 (기상 데이터도 연도별로 따로 받음)

set -e

START=${1:-2024-01}
END=${2:-2024-06}

# 센트럴파크(WBAN 94728) 관측소 - NOAA LCD 시간별 기상 데이터
WEATHER_STATION=72505394728

DATA_DIR="data"
mkdir -p "$DATA_DIR"

start_year=${START%-*}
start_month=${START#*-}
end_year=${END%-*}
end_month=${END#*-}

# 10# 접두어는 "08", "09"처럼 0으로 시작하는 값이 8진수로 잘못 해석되는 걸 방지
start_idx=$((10#$start_year * 12 + 10#$start_month))
end_idx=$((10#$end_year * 12 + 10#$end_month))

if [ "$start_idx" -gt "$end_idx" ]; then
    echo "start_month(${START})가 end_month(${END})보다 뒤입니다."
    exit 1
fi

echo "=== TLC 운행 기록(Yellow Taxi) 다운로드: ${START} ~ ${END} ==="
years_seen=""
idx=$start_idx
while [ "$idx" -le "$end_idx" ]; do
    year=$((idx / 12))
    month=$((idx % 12))
    if [ "$month" -eq 0 ]; then
        month=12
        year=$((year - 1))
    fi
    ym=$(printf "%04d-%02d" "$year" "$month")
    file="yellow_tripdata_${ym}.parquet"

    if [ -f "${DATA_DIR}/${file}" ]; then
        echo "  ${file} 이미 있음, 건너뜀"
    else
        echo "  ${file} 다운로드 중..."
        curl -L -s -o "${DATA_DIR}/${file}" "https://d37ci6vzurychx.cloudfront.net/trip-data/${file}"
    fi

    # 이번 파이프라인에서 다룬 연도들을 기록해뒀다가, 아래에서 연도별 기상 데이터를 한 번씩만 받음
    case " $years_seen " in
        *" $year "*) ;;
        *) years_seen="$years_seen $year" ;;
    esac

    idx=$((idx + 1))
done

echo ""
echo "=== 기상 데이터(NOAA LCD, 센트럴파크 station ${WEATHER_STATION}) 다운로드 ==="
for year in $years_seen; do
    weather_file="weather_${year}_central_park.csv"
    if [ -f "${DATA_DIR}/${weather_file}" ]; then
        echo "  ${weather_file} 이미 있음, 건너뜀"
    else
        echo "  ${weather_file} 다운로드 중..."
        curl -L -s -o "${DATA_DIR}/${weather_file}" \
            "https://www.ncei.noaa.gov/data/local-climatological-data/access/${year}/${WEATHER_STATION}.csv"
    fi
done

echo ""
echo "완료. data/ 폴더 내용:"
ls -lh "$DATA_DIR"
