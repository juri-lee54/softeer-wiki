# W3M5 — Hadoop MapReduce 기반 영화 평균 평점 계산

MovieLens 20M 데이터셋(`ratings.csv`)을 Hadoop Streaming(Python Mapper/Reducer)으로 처리하여,
영화(movieId)별 평균 평점을 계산하는 MapReduce 작업이다.

## 1. 디렉토리 구조

```
W3M5/
├── docker-compose.yml      # Hadoop 클러스터 (master, worker1, worker2)
├── Dockerfile
├── config/                 # Hadoop 설정 파일 (core-site.xml, hdfs-site.xml, ...)
├── sample/
│   └── ratings.csv          # MovieLens 20M 평점 데이터 (master 컨테이너의 /sample 로 마운트)
├── scripts/
│   ├── mapper.py             # Mapper
│   └── reducer.py            # Reducer
└── README.md
```

<br>

## 2. 데이터셋

- **MovieLens 20M** (`ratings.csv`)
- 컬럼 구성 (첫 줄에 헤더 포함, UTF-8 인코딩):

  | index | 0      | 1       | 2      | 3         |
  |-------|--------|---------|--------|-----------|
  | 컬럼  | userId | movieId | rating | timestamp |

  약 2천만 건(20,000,263건)의 평점, 26,744개의 영화에 대한 데이터가 담겨 있다.
- `sample/ratings.csv` 로 저장했으며, `docker-compose.yml`의 volume 설정에 따라 master 컨테이너 내부 `/sample/ratings.csv` 경로에서 접근된다.

<br>

## 3. 프로그램 설명

### Mapper (`scripts/mapper.py`)

- 평점 한 줄(CSV row)을 콤마 기준으로 분리하여 `movieId`(1번 컬럼), `rating`(2번 컬럼)만 추출한다.
- `rating`을 `float`으로 변환하는 과정에서 컬럼 수 부족(`IndexError`) 또는 숫자로 변환 불가능한 값(`ValueError`)이 발생하면 해당 줄을 건너뛴다.
  - 첫 줄의 헤더(`userId,movieId,rating,timestamp`)는 `rating` 자리의 문자열 `"rating"`이 `float()` 변환에 실패하므로, 별도 처리 없이 이 예외 처리 로직으로 자연스럽게 걸러진다.
- 한 줄당 `<movieId>\t<rating>` 형식으로 출력한다.

### Reducer (`scripts/reducer.py`)

- Hadoop이 키(movieId) 기준으로 정렬해서 넘겨주는 `<movieId>\t<rating>` 스트림을 입력받는다.
- 같은 movieId가 연속되는 동안 평점의 합(`sum_rating`)과 개수(`count`)를 누적하다가, key가 바뀌는 시점에 그동안의 평균을 출력하고 누적값을 초기화하는 표준 스트리밍 Reducer 패턴을 사용한다.
- 스트림이 끝난 뒤 마지막으로 누적 중이던 movieId도 한 번 더 flush하여 출력에서 누락되지 않도록 한다.
- 평균은 소수점 둘째 자리에서 반올림하여 `<movieId>\t<평균 평점>` (소수점 첫째 자리까지) 형식으로 출력한다.

<br>

## 4. 실행 방법

### 4.1 Hadoop 클러스터 기동

```bash
cd DE/missions/W3/W3M5
docker compose build master
docker compose up -d
docker exec -it master bash
```

컨테이너 안에서 데몬이 정상적으로 떠 있는지 확인한다.

```bash
jps
```

### 4.2 입력 데이터를 HDFS에 업로드

```bash
hdfs dfs -mkdir -p /user/jurilee/input
hdfs dfs -put /sample/ratings.csv /user/jurilee/input/
hdfs dfs -ls /user/jurilee/input/
```

로컬 파일 크기(약 533MB)와 HDFS에 올라간 파일 크기가 일치하는지 확인한다.

### 4.3 로컬 파이프라인으로 Mapper/Reducer 사전 검증

Hadoop에 제출하기 전에, 로컬에서 Mapper → sort → Reducer 순서로 먼저 검증한다.

```bash
head -100 sample/ratings.csv | python3 scripts/mapper.py | sort | python3 scripts/reducer.py
```

특정 movieId 하나를 골라 여러 평점이 정확히 합산·평균되는지도 함께 확인한다.

```bash
grep -E ',296,' sample/ratings.csv | python3 scripts/mapper.py | sort | python3 scripts/reducer.py
# 296  4.2
```

movieId `296`(Pulp Fiction)은 공개적으로 알려진 평균 평점이 약 4.17이며, 계산 결과(반올림 후 4.2)가 이와 일치하므로 로직이 정확함을 확인할 수 있다.

### 4.4 Hadoop Streaming 작업 제출

컨테이너(`master`) 안에서 실행한다.

```bash
hadoop jar $HADOOP_HOME/share/hadoop/tools/lib/hadoop-streaming-*.jar \
  -D mapreduce.job.reduces=2 \
  -input /user/jurilee/input/ratings.csv \
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

### 4.5 작업 진행 상황 모니터링

- **CLI**: 제출 시 출력되는 `Running job: job_...` 로그에서 `map N% reduce N%` 진행률을 확인한다.
- **YARN 웹 UI**: 호스트 브라우저에서 `http://localhost:8088` 접속(docker-compose에서 8088 포트를 매핑해둠) → 해당 Application 클릭 후 진행 상태/카운터를 확인한다.
- 잡 종료 시 콘솔에 `Job job_... completed successfully` 와 함께 Counters(처리 레코드 수 등)가 출력된다.

### 4.6 결과 조회

```bash
hdfs dfs -ls /user/jurilee/output
hdfs dfs -cat /user/jurilee/output/part-*
```

Reducer를 2개 사용했기 때문에 출력이 `part-00000`, `part-00001` 두 개 파일로 나뉘어 생성되며, `part-*` 로 한 번에 조회한다.

<br>

## 5. 결과

```
1       3.9
10      3.4
100     3.2
1000    3.1
100006  2.5
100008  3.3
100013  3.3
100015  2.0
100017  3.1
...
```

전체 결과는 `part-00000`, `part-00001` 두 파일에 걸쳐 총 26,744줄이 생성된다.

<br>

## 6. 결과 해석 및 검증

1. **`_SUCCESS` 파일 확인**
   `hdfs dfs -ls /user/jurilee/output` 결과에 `_SUCCESS` 파일이 존재하면 job이 오류 없이 정상 종료되었음을 의미한다.

2. **출력 레코드 수 검증**
   ```bash
   hdfs dfs -cat /user/jurilee/output/part-00000 /user/jurilee/output/part-00001 | wc -l
   # 26744
   ```
   MovieLens 20M 데이터셋에서 실제로 평점이 매겨진 고유 영화(movieId) 수는 26,744개로 알려져 있다. 출력 줄 수가 이와 정확히 일치하므로, 모든 영화가 누락·중복 없이 정확히 한 줄씩 집계되었음을 확인할 수 있다.

3. **알려진 값과의 교차 검증**
   ```bash
   hdfs dfs -cat /user/jurilee/output/part-00000 /user/jurilee/output/part-00001 | grep -P '^296\t'
   # 296  4.2
   ```
   movieId `296`(Pulp Fiction)의 결과가 4.3절에서 로컬로 미리 검증한 값(4.2), 그리고 공개적으로 알려진 실제 평균 평점(약 4.17)과 일치하므로 클러스터 실행 결과도 정확함을 확인할 수 있다.

4. **Job Counters 교차 확인**
   ```bash
   hadoop job -status <job_id>
   ```
   또는 제출 시 출력된 Counters 블록에서 `Map input records`(전체 평점 수, 20,000,263)와 `Reduce output records`(26,744, 위 2번 항목과 동일)를 통해 처리 규모가 예상과 일치하는지 확인한다.

<br>

## 7. 소스 코드

- Mapper: [`scripts/mapper.py`](scripts/mapper.py)
- Reducer: [`scripts/reducer.py`](scripts/reducer.py)
