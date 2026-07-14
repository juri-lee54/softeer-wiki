# W3M4 — Hadoop MapReduce 기반 트위터 감정 분석

Sentiment140 트위터 데이터셋을 Hadoop Streaming(Python Mapper/Reducer)으로 처리하여,
트윗을 positive / negative / neutral 세 범주로 분류하고 각 범주별 개수를 집계하는 MapReduce 작업이다.

## 1. 디렉토리 구조

```
W3M4/
├── docker-compose.yml      # Hadoop 클러스터 (master, worker1, worker2)
├── Dockerfile
├── config/                 # Hadoop 설정 파일 (core-site.xml, hdfs-site.xml, ...)
├── sample/
│   └── twit-data.csv        # Sentiment140 데이터셋 (master 컨테이너의 /sample 로 마운트)
├── scripts/
│   ├── mapper.py             # Mapper
│   └── reducer.py            # Reducer (Combiner로도 재사용)
└── README.md
```

<br>

## 2. 데이터셋

- **Sentiment140** (`training.1600000.processed.noemoticon.csv`)
- 컬럼 구성 (헤더 없음, `latin-1` 인코딩):

  | index | 0        | 1  | 2    | 3     | 4    | 5    |
  |-------|----------|----|------|-------|------|------|
  | 컬럼  | polarity | id | date | query | user | text |

  트윗 본문은 마지막(5번, 0-based) 컬럼에 있다.
- `sample/twit-data.csv` 로 저장했으며, `docker-compose.yml`의 volume 설정에 따라 master 컨테이너 내부 `/sample/twit-data.csv` 경로에서 접근된다.

<br>

## 3. 프로그램 설명

### Mapper (`scripts/mapper.py`)

- 트윗 한 줄(CSV row)을 읽어 `text` 컬럼만 추출한다.
  
- 텍스트를 소문자화 후 단어 단위로 토큰화(`\w` 및 `'` 포함 정규식)한다.
- 미리 정의한 `POSITIVE_WORDS`, `NEGATIVE_WORDS` 키워드 집합과 비교하여 각각 매칭된 단어 수를 센다.
  - positive 단어 수 > negative 단어 수 → `positive`
  - positive 단어 수 < negative 단어 수 → `negative`
  - 그 외(동점, 둘 다 0 포함) → `neutral`
- 트윗 하나당 `<category>\t1` 형식으로 한 줄씩 출력한다.
- CSV 파싱 실패(`csv.Error`), 컬럼 누락(`IndexError`), 빈 줄은 건너뛴다.

### Reducer (`scripts/reducer.py`)

- Hadoop이 키(카테고리) 기준으로 정렬해서 넘겨주는 `<category>\t1` 스트림을 입력받는다.
- 같은 키가 연속되는 동안 카운트를 누적하다가 키가 바뀌면 그때까지의 합을 출력하는 표준 스트리밍 Reducer 패턴을 사용한다.
- 동일한 스크립트를 Combiner로도 그대로 재사용한다 (Mapper 출력의 합과 최종 합이 동일하게 나옴을 이용).

<br>

## 4. 실행 방법

### 4.1 Hadoop 클러스터 기동

```bash
cd DE/missions/W3/W3M4
docker-compose up -d
docker exec -it master bash
```

컨테이너 안에서 데몬이 정상적으로 떠 있는지 확인한다.

```bash
jps
```

### 4.2 입력 데이터를 HDFS에 업로드

```bash
hdfs dfs -mkdir -p /user/jurilee/input
hdfs dfs -put /sample/twit-data.csv /user/jurilee/input/
hdfs dfs -ls /user/jurilee/input/
```

업로드가 잘 됐는지 확인한다:

```bash
hdfs dfs -cat /user/jurilee/input/twit-data.csv | head -5
```

### 4.3 로컬 파이프라인으로 Mapper/Reducer 사전 검증

Hadoop에 제출하기 전에, 로컬에서 Mapper → sort → Reducer 순서로 먼저 검증한다.

```bash
head -1000 sample/twit-data.csv | python3 scripts/mapper.py | sort | python3 scripts/reducer.py
```

`positive` / `negative` / `neutral` 세 줄이 출력되고, 세 값의 합이 처리한 줄 수와 일치하면 정상이다.

### 4.4 Hadoop Streaming 작업 제출

컨테이너(`master`) 안에서 실행한다.

```bash
hadoop jar $HADOOP_HOME/share/hadoop/tools/lib/hadoop-streaming-*.jar \
  -D mapreduce.job.reduces=2 \
  -D mapreduce.input.fileinputformat.split.maxsize=524288 \
  -input /user/jurilee/input/twit-data.csv \
  -output /user/jurilee/output \
  -mapper /scripts/mapper.py \
  -reducer /scripts/reducer.py \
  -combiner /scripts/reducer.py \
  -file /scripts/mapper.py \
  -file /scripts/reducer.py
```

- `-input` / `-output`: HDFS 상의 입출력 경로. `-output` 경로는 실행 전에 존재하지 않아야 한다(이미 있으면 `hdfs dfs -rm -r /user/jurilee/output` 로 삭제 후 재실행).
- `-mapper` / `-reducer`: 각 단계에서 실행할 스크립트.
- `-combiner`: Reducer와 동일한 스크립트를 사용해 Map 단계에서 부분 집계를 미리 수행, 셔플 데이터량을 줄인다.
- `-file`: mapper.py / reducer.py를 각 태스크로 배포한다.

### 4.5 작업 진행 상황 모니터링

- **CLI**: 제출 시 출력되는 `Running job: job_...` 로그에서 `map N% reduce N%` 진행률을 확인한다.
- **YARN 웹 UI**: 호스트 브라우저에서 `http://localhost:8088` 접속 (docker-compose에서 8088 포트를 매핑해둠) → 해당 Application 클릭 후 진행 상태/카운터를 확인한다.
- 잡 종료 시 콘솔에 `Job job_... completed successfully` 와 함께 Counters(처리 레코드 수 등)가 출력된다.

### 4.6 결과 조회

```bash
hdfs dfs -ls /user/jurilee/output
hdfs dfs -cat /user/jurilee/output/part-*
```

`-D mapreduce.job.reduces=2` 로 Reducer를 2개 사용했기 때문에 출력이 `part-00000`, `part-00001` 두 개 파일로 나뉘어 생성되며, `part-*` 로 한 번에 조회한다.

<br>

## 5. 결과

```
negative        213782
neutral 964679
positive        421539
```

<br>

## 6. 결과 해석 및 검증

1. **정합성 검증(레코드 수 일치 여부)**
   Job Counters의 `Map input records`(=전체 트윗 수, 1,600,000)와 출력된 세 카테고리 합을 비교한다.

   ```
   213782 + 964679 + 421539 = 1,600,000
   ```

   `Map input records`와 정확히 일치하므로, 모든 트윗이 누락·중복 없이 정확히 하나의 카테고리로 분류·집계되었음을 확인할 수 있다.

2. **Job Counters 교차 확인**
   ```
   hadoop job -status <job_id>
   ```
   또는 제출 시 출력된 Counters 블록에서 `Map output records`, `Reduce output records` 값을 통해 Mapper가 트윗 1건당 정확히 1건씩 출력했는지(`Map input records == Map output records`), 최종 카테고리 수가 3개인지(`Reduce output records == 3`)를 확인한다.

3. **분포의 합리성 확인**
   키워드 사전에 매칭되는 단어가 없는 일반적인 트윗은 모두 `neutral`로 분류되는 구조이므로, `neutral` 비중이 가장 높게 나오는 것은 설계상 자연스러운 결과이다.

<br>

## 7. 소스 코드

- Mapper: [`scripts/mapper.py`](scripts/mapper.py)
- Reducer: [`scripts/reducer.py`](scripts/reducer.py)
