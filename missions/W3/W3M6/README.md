# W3M6 — Hadoop MapReduce 기반 Amazon 제품 리뷰 집계

Amazon Reviews 2023 데이터셋(`Movies_and_TV.csv`)을 Hadoop Streaming(Python Mapper/Reducer)으로 처리하여,
제품(parent_asin)별 리뷰 수와 평균 평점을 계산하고 가장 많은 리뷰를 받은 제품을 찾는 MapReduce 작업이다.

## 1. 디렉토리 구조

```
W3M6/
├── docker-compose.yml      # Hadoop 클러스터 (master, worker1, worker2)
├── Dockerfile
├── config/                 # Hadoop 설정 파일 (core-site.xml, hdfs-site.xml, ...)
├── sample/
│   └── Movies_and_TV.csv    # Amazon Reviews 2023 평점 데이터 (master 컨테이너의 /sample 로 마운트)
├── scripts/
│   ├── mapper.py             # Mapper
│   └── reducer.py            # Reducer
└── README.md
```

<br>

## 2. 데이터셋

- **Amazon Reviews 2023** ([McAuley Lab, UCSD](https://amazon-reviews-2023.github.io/))
- 33개 카테고리 중 `Movies_and_TV` 카테고리의 **Pure IDs (0-core, rating only)** 파일을 사용한다.
  - 다운로드 URL: `https://mcauleylab.ucsd.edu/public_datasets/data/amazon_2023/benchmark/0core/rating_only/Movies_and_TV.csv.gz`
  - 리뷰 텍스트 없이 `user_id, parent_asin(제품 ID), rating, timestamp` 네 컬럼만 담은 압축 CSV로, 이번 과제(제품ID·평점 집계)에 정확히 맞는 형식이다.
- 컬럼 구성 (첫 줄에 헤더 포함, UTF-8 인코딩):

  | index | 0       | 1           | 2      | 3         |
  |-------|---------|-------------|--------|-----------|
  | 컬럼  | user_id | parent_asin | rating | timestamp |

  압축 해제 시 약 949MB, 17,158,519건의 리뷰(헤더 제외) 데이터가 담겨 있다.
- `sample/Movies_and_TV.csv` 로 저장했으며, `docker-compose.yml`의 volume 설정에 따라 master 컨테이너 내부 `/sample/Movies_and_TV.csv` 경로에서 접근된다.

<br>

## 3. 프로그램 설명

### Mapper (`scripts/mapper.py`)

- 리뷰 한 줄(CSV row)을 콤마 기준으로 분리하여 `parent_asin`(1번 컬럼, 제품 ID), `rating`(2번 컬럼)만 추출한다.
- `rating`을 `float`으로 변환하는 과정에서 컬럼 수 부족(`IndexError`) 또는 숫자로 변환 불가능한 값(`ValueError`)이 발생하면 해당 줄을 건너뛴다.
  - 첫 줄의 헤더(`user_id,parent_asin,rating,timestamp`)는 `rating` 자리의 문자열 `"rating"`이 `float()` 변환에 실패하므로, 별도 처리 없이 이 예외 처리 로직으로 자연스럽게 걸러진다.
- 한 줄당 `<parent_asin>\t<rating>` 형식으로 출력한다.

### Reducer (`scripts/reducer.py`)

- Hadoop이 키(parent_asin) 기준으로 정렬해서 넘겨주는 `<parent_asin>\t<rating>` 스트림을 입력받는다.
- 같은 parent_asin이 연속되는 동안 평점의 합(`sum_rating`)과 리뷰 개수(`count`)를 누적하다가, key가 바뀌는 시점에 그동안의 리뷰 수와 평균을 출력하고 누적값을 초기화하는 표준 스트리밍 Reducer 패턴을 사용한다.
- 스트림이 끝난 뒤 마지막으로 누적 중이던 parent_asin도 한 번 더 flush하여 출력에서 누락되지 않도록 한다.
- 평균은 소수점 둘째 자리에서 반올림하여 `<parent_asin>\t<리뷰 수>\t<평균 평점>` (소수점 첫째 자리까지) 형식으로 출력한다.

<br>

## 4. 실행 방법

### 4.1 데이터셋 다운로드

```bash
cd DE/missions/W3/W3M6
mkdir -p sample
curl -o sample/Movies_and_TV.csv.gz \
  "https://mcauleylab.ucsd.edu/public_datasets/data/amazon_2023/benchmark/0core/rating_only/Movies_and_TV.csv.gz"
gunzip sample/Movies_and_TV.csv.gz
```

### 4.2 Hadoop 클러스터 기동

```bash
docker compose build master
docker compose up -d
docker exec -it master bash
```

컨테이너 안에서 데몬이 정상적으로 떠 있는지 확인한다.

```bash
jps
```

### 4.3 입력 데이터를 HDFS에 업로드

```bash
hdfs dfs -mkdir -p /user/jurilee/input
hdfs dfs -put /sample/Movies_and_TV.csv /user/jurilee/input/
hdfs dfs -ls -h /user/jurilee/input/
```

로컬 파일 크기(약 949MB)와 HDFS에 올라간 파일 크기가 일치하는지 확인한다.

### 4.4 로컬 파이프라인으로 Mapper/Reducer 사전 검증

Hadoop에 제출하기 전에, 로컬에서 Mapper → sort → Reducer 순서로 먼저 검증한다.

```bash
head -100 sample/Movies_and_TV.csv | python3 scripts/mapper.py | sort | python3 scripts/reducer.py
```

특정 제품 하나를 골라 여러 평점이 정확히 합산·평균되는지도 함께 확인한다.

```bash
grep ',B013488XFS,' sample/Movies_and_TV.csv | python3 scripts/mapper.py | sort | python3 scripts/reducer.py
# B013488XFS    5520    4.5
```

`cut`/`sort`/`uniq`로 구한 로컬 집계 값(리뷰 5,520건)과 Reducer 출력의 리뷰 수가 일치하므로 로직이 정확함을 확인할 수 있다.

### 4.5 Hadoop Streaming 작업 제출

컨테이너(`master`) 안에서 실행한다.

```bash
hadoop jar $HADOOP_HOME/share/hadoop/tools/lib/hadoop-streaming-*.jar \
  -D mapreduce.job.reduces=2 \
  -input /user/jurilee/input/Movies_and_TV.csv \
  -output /user/jurilee/output \
  -mapper /scripts/mapper.py \
  -reducer /scripts/reducer.py \
  -file /scripts/mapper.py \
  -file /scripts/reducer.py
```

- `-input` / `-output`: HDFS 상의 입출력 경로. `-output` 경로는 실행 전에 존재하지 않아야 한다(이미 있으면 `hdfs dfs -rm -r /user/jurilee/output` 로 삭제 후 재실행).
- `-mapper` / `-reducer`: 각 단계에서 실행할 스크립트.
- `-D mapreduce.job.reduces=2`: Reducer를 2개 사용하여 워커 노드 2대에 분산 처리한다.
- `-file`: mapper.py / reducer.py를 각 태스크로 배포한다.

### 4.6 작업 진행 상황 모니터링

- **CLI**: 제출 시 출력되는 `Running job: job_...` 로그에서 `map N% reduce N%` 진행률을 확인한다.
- **YARN 웹 UI**: 호스트 브라우저에서 `http://localhost:8088` 접속(docker-compose에서 8088 포트를 매핑해둠) → 해당 Application 클릭 후 진행 상태/카운터를 확인한다.
- 잡 종료 시 콘솔에 `Job job_... completed successfully` 와 함께 Counters(처리 레코드 수 등)가 출력된다.

### 4.7 결과 조회

```bash
hdfs dfs -ls /user/jurilee/output
hdfs dfs -cat /user/jurilee/output/part-*
```

Reducer를 2개 사용했기 때문에 출력이 `part-00000`, `part-00001` 두 개 파일로 나뉘어 생성되며, `part-*` 로 한 번에 조회한다.

<br>

## 5. 결과

가장 많은 리뷰를 받은 제품 상위 5개 (`sort -t$'\t' -k2 -rn`):

```
B00RSGIVVO      61713   4.5
B00I3MQNWG      55962   4.6
B01J4SRJFW      47814   4.7
B01AB17IGQ      28719   4.8
B01J94A5GQ      27275   4.6
```

전체 결과는 `part-00000`, `part-00001` 두 파일에 걸쳐 총 747,764줄(고유 제품 수)이 생성된다.

<br>

## 6. 결과 해석 및 검증

1. **`_SUCCESS` 파일 확인**
   `hdfs dfs -ls /user/jurilee/output` 결과에 `_SUCCESS` 파일이 존재하면 job이 오류 없이 정상 종료되었음을 의미한다.

2. **출력 레코드 수 검증**
   ```bash
   hdfs dfs -cat /user/jurilee/output/part-00000 /user/jurilee/output/part-00001 | wc -l
   ```
   로컬에서 `cut -d',' -f2 sample/Movies_and_TV.csv | tail -n +2 | sort -u | wc -l` 로 구한 고유 제품(parent_asin) 수와 비교하여, 모든 제품이 누락·중복 없이 정확히 한 줄씩 집계되었는지 확인한다.

3. **알려진 값과의 교차 검증**
   ```bash
   hdfs dfs -cat /user/jurilee/output/part-* | grep -P '^B00RSGIVVO\t'
   # B00RSGIVVO    61713   4.5
   ```
   로컬에서 `cut`/`sort`/`uniq -c`로 미리 구한 최다 리뷰 제품(`B00RSGIVVO`, 61,713건)의 리뷰 수와 클러스터 실행 결과가 정확히 일치하므로, 분산 처리 결과가 정확함을 확인할 수 있다.

4. **Job Counters 교차 확인**
   ```bash
   hadoop job -status <job_id>
   ```
   또는 제출 시 출력된 Counters 블록에서 `Map input records`(17,158,520, 헤더 포함)와 `Map output records`(17,158,519, 헤더 한 줄이 파싱 실패로 필터링됨), `Reduce output records`(747,764, 2번 항목과 동일한 고유 제품 수)를 통해 처리 규모가 예상과 일치하는지 확인한다.

<br>

## 7. 소스 코드

- Mapper: [`scripts/mapper.py`](scripts/mapper.py)
- Reducer: [`scripts/reducer.py`](scripts/reducer.py)
