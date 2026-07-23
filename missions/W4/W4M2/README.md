# NYC TLC 운행 데이터 분석 (Spark on Docker)

Docker로 Apache Spark 독립형(standalone) 클러스터(마스터 1 + 워커 2)를 구성하고,
뉴욕시 TLC(Taxi & Limousine Commission) 운행 기록을 정제·집계·분석한 뒤
Jupyter Notebook으로 시각화하는 프로젝트다.

## 디렉토리 구조

```
W4M2/
├── Dockerfile             # Spark 노드(마스터/워커/Jupyter 공용) 이미지 정의
├── entrypoint.sh          # SPARK_MODE(master/worker)에 따라 실행할 프로세스 분기
├── docker-compose.yml     # 마스터 1 + 워커 2 + Jupyter 클러스터 구성
├── submit.sh              # spark-submit으로 jobs/ 아래 지정한 작업을 제출하는 스크립트
├── download_data.sh       # TLC 운행 기록 + NOAA 기상 데이터를 data/ 폴더에 받는 스크립트
├── jobs/
│   ├── clean_trips.py         # TLC 운행 기록 로딩 + 결측값/이상치 클리닝
│   ├── compute_metrics.py     # 평균 이동시간/거리 집계
│   ├── peak_hours.py          # 시간대별 운행 분포 + 피크 시간대 계산
│   └── weather_correlation.py # 기상 데이터와 운행 수요 상관관계 통계 검증
├── data/
│   ├── yellow_tripdata_2023-12~2024-06.parquet  # TLC 운행 기록 (2023-12~2024-06, Yellow Taxi)
│   ├── weather_2023_central_park.csv            # NOAA LCD 센트럴파크 관측소 2023년 시간별 기상 데이터
│   └── weather_2024_central_park.csv            # NOAA LCD 센트럴파크 관측소 2024년 시간별 기상 데이터
├── notebooks/
│   └── analysis.ipynb     # 결과 시각화 노트북 (Jupyter Lab에서 실행)
└── output/                # 각 job의 결과가 저장되는 위치 (최초 실행 후 생성됨)
```

## 사전 준비

- Docker Desktop이 설치되어 있고 실행 중이어야 한다
- 이 저장소를 로컬에 clone/다운로드한다

## 1. 이미지 빌드 + 클러스터 기동

```bash
cd DE/missions/W4/W4M2
docker-compose up --build -d
```

- 최초 빌드 시 Spark 배포판과 pandas/scipy/jupyterlab 등 파이썬 패키지를 받으므로 몇 분 걸릴 수 있다
- `-d`는 백그라운드 실행 옵션이다

## 2. 클러스터 상태 확인

```bash
docker-compose ps
```

`spark-master`, `spark-worker-1`, `spark-worker-2`, `jupyter` 네 컨테이너가 모두 `Up` 상태인지 확인한다.

브라우저에서 아래 URL로 접속해 상태를 확인한다.

- 마스터 웹 UI: http://localhost:8080 (Workers 섹션에 2개 등록되어 있어야 함)
- 워커 1 웹 UI: http://localhost:8081
- 워커 2 웹 UI: http://localhost:8082
- Jupyter Lab: http://localhost:8888/lab?token=softeer-dev-token

## 3. 데이터 준비

`data/`에 이미 2023년 12월~2024년 6월(7개월, 2개 연도) Yellow Taxi 운행 기록(Parquet)과
센트럴파크 관측소의 2023/2024년 기상 데이터(CSV)가 들어있다.
없거나 기간을 더 늘리고 싶으면 `download_data.sh`로 받는다.

```bash
chmod +x download_data.sh

./download_data.sh                    # 기본값(2024-01 ~ 2024-06) 다운로드
./download_data.sh 2024-01 2024-06    # 위와 동일, 기간을 명시적으로 지정
./download_data.sh 2023-12 2024-06    # 연도가 걸쳐 있어도 됨 - 기상 데이터도 연도별로 따로 받아옴
```

- TLC 운행 기록: [NYC TLC 공식 페이지](https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page)에서 배포하는 `yellow_tripdata_YYYY-MM.parquet`
- 기상 데이터: [NOAA Local Climatological Data](https://www.ncei.noaa.gov/products/land-based-station/local-climatological-data)의 센트럴파크 관측소(WBAN 94728, station id `72505394728`) 연도별 시간별 관측 CSV
- 이미 받아둔 파일은 건너뛰므로 여러 번 실행해도 안전하다
- 파일명 패턴(`yellow_tripdata_*`)만 맞으면 `clean_trips.py`가 `data/` 안의 모든 달치를 자동으로 읽는다 — **Parquet(`.parquet`)과 CSV(`.csv`)를 섞어놔도 둘 다 읽어서 합친다** (컬럼명 기준 union)
- `weather_correlation.py`도 `weather_*_central_park.csv` 글롭 패턴으로 여러 해 파일을 한 번에 읽으므로, 운행 기록이 여러 연도에 걸쳐 있어도 해당 연도의 기상 파일만 받아두면 자동으로 매칭된다

## 4. 작업 제출

```bash
chmod +x submit.sh
```

파이프라인 순서대로 4개 job을 실행한다. (인자를 생략하면 각 job에 정의된 기본 입출력 경로를 사용)

```bash
./submit.sh clean_trips
./submit.sh compute_metrics
./submit.sh peak_hours
./submit.sh weather_correlation
```

입력/출력 경로를 바꾸고 싶다면 job 이름 뒤에 인자로 전달한다 (모두 컨테이너 내부 기준 경로).

```bash
./submit.sh clean_trips /opt/data /opt/output/cleaned_trips
```

## 5. 결과 확인

각 job은 실행 로그에 결과를 사람이 읽기 쉬운 형태로 출력한다. 예:

```
Raw records: 23708660
Cleaned records: 23269365 (98.1% kept)
```

```
Average trip duration: 17.18 minutes
Average trip distance: 3.36 miles
```

```
Peak hour: 18:00 with 1,659,438 trips
```

```
Temperature vs trip count: r=0.217, p=0.0000
T-test (rainy vs dry hourly trip counts): t=-0.143, p=0.8860
```

출력 파일은 볼륨 마운트를 통해 호스트에서 바로 확인 가능하다.

```bash
ls output/
cat output/trip_metrics/part-*.csv
cat output/peak_hours/part-*.csv
cat output/weather_correlation/stats_summary/part-*.csv
```

| job | 결과 위치 | 내용 |
|---|---|---|
| clean_trips | `output/cleaned_trips/` | 정제된 운행 기록 (Parquet) |
| compute_metrics | `output/trip_metrics/` | 평균 이동시간/거리 (CSV) |
| peak_hours | `output/peak_hours/` | 시간대별 운행 건수 + 피크 시간대 표시 (CSV) |
| weather_correlation | `output/weather_correlation/hourly_joined/` | 시간별 운행건수+기온+강수량 결합 테이블 (CSV) |
| weather_correlation | `output/weather_correlation/stats_summary/` | 상관계수/t-검정 결과 (CSV) |

Spark 웹 UI(http://localhost:8080)의 `Completed Applications`에서도 작업 실행 이력을 확인할 수 있다.

## 6. Jupyter Notebook으로 시각화

http://localhost:8888/lab?token=softeer-dev-token 접속 후 `notebooks/analysis.ipynb`를 열어 위에서부터 순서대로 실행한다
(`Run > Run All Cells`). `output/`에 저장된 CSV들을 pandas로 읽어와 다음을 그린다.

- 피크 시간대 막대그래프 (피크 시간대만 강조 표시)
- 시간별 운행건수 vs 기온 라인차트, 온도-운행건수 산점도
- 비/눈 오는 시간 vs 안 오는 시간 평균 운행건수 비교 막대그래프

job을 다시 돌려 `output/` 내용이 갱신되면, 노트북도 `Run All Cells`로 재실행만 하면 최신 결과가 반영된다.

터미널에서 노트북을 직접 실행해 결과를 갱신할 수도 있다.

```bash
docker exec jupyter jupyter nbconvert --to notebook --execute --inplace /opt/notebooks/analysis.ipynb
```

## 7. 로그 / 디버깅

```bash
docker logs spark-master
docker logs spark-worker-1
docker logs spark-worker-2
docker logs jupyter
```

- 워커가 마스터에 접속하지 못하면 `spark-worker-*` 로그에 연결 재시도 메시지가 반복된다.
  이 경우 `docker-compose.yml`의 `SPARK_MASTER_URL` 값과 마스터 컨테이너 상태를 확인한다.
- `entrypoint.sh`는 `SPARK_MODE` 값이 `master`/`worker`가 아니면 에러 메시지를 출력하고 종료한다.
  Jupyter 서비스는 `entrypoint`를 비워서 이 스크립트를 거치지 않고 바로 `jupyter lab`을 실행한다.

## 8. 정리

```bash
docker-compose down
```
