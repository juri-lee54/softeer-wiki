# W3M3 - Hadoop MapReduce 단어 수 세기 (Word Count)

## 1. 개요

Hadoop MapReduce 프레임워크를 이용해 대용량 전자책 텍스트에서 각 단어의 출현 횟수를 세는 프로그램을 작성하고 실행한다. Python으로 Mapper/Reducer를 구현하고, Hadoop Streaming을 통해 멀티노드(worker 2대) 클러스터에서 분산 실행한다.

<br>

## 2. 사용한 전자책

- 제목: Designing Data-Intensive Applications
- 저자: Martin Kleppmann
- 파일: `DDIA.pdf`를 `pdftotext`로 변환한 `DDIA.txt` (약 22.5만 단어, 200페이지 이상 분량)
- URL: https://github.com/aasthas2022/SDE-Interview-and-Prep-Roadmap/blob/main/System%20Design/Resources/Designing%20Data%20Intensive%20Applications%20by%20Martin%20Kleppmann.pdf

<br>

## 3. 디렉토리 구조

```
W3M3/
├── Dockerfile              # Hadoop 노드 공통 이미지 정의
├── docker-compose.yml      # master + worker1 + worker2 클러스터 구성
├── entrypoint.sh           # 컨테이너 시작 시 노드 타입별 초기화 스크립트
├── config/                 # core-site.xml, hdfs-site.xml 등 Hadoop 설정
├── scripts/
│   ├── mapper.py
│   └── reducer.py
├── sample/
│   └── DDIA.txt            # HDFS 업로드용 전자책 텍스트
└── data/                   # 각 노드의 HDFS 로컬 데이터 디렉토리(볼륨 마운트)
```

`sample/`과 `scripts/`는 각각 master 컨테이너의 `/sample`, `/scripts` 경로에 볼륨 마운트되어 있어, 호스트에서 파일을 수정하면 컨테이너 안에서도 바로 반영된다.

<br>

## 4. 환경 구성

- Docker Compose 기반 Hadoop 멀티노드 클러스터: `master`(NameNode + ResourceManager), `worker1`, `worker2`(DataNode + NodeManager)
- Hadoop 3.3.6, Python 3

클러스터 기동 절차는 다음과 같다.

```bash
docker compose build
docker compose up -d
docker exec -it master bash
jps   # NameNode, ResourceManager 등이 정상 기동됐는지 확인
```

<br>

## 5. 전자책 준비

전자책은 PDF로 배포되므로, Hadoop Streaming이 줄 단위 텍스트로 읽을 수 있도록 사전에 plain text로 변환한다.

```bash
pdftotext ./sample/DDIA.pdf ./sample/DDIA.txt
wc -w ./sample/DDIA.txt   # 총 단어 수를 미리 확인해 검증 기준값으로 삼는다
# 225290 단어
```

<br>

## 6. 소스 코드

### 6.1 Mapper (`scripts/mapper.py`)

텍스트를 한 줄씩 읽어 단어 단위로 토큰화하고, 각 단어에 대해 `단어\t1` 형태의 키-값 쌍을 출력한다.

```python
#!/usr/bin/env python3
import sys
import re

WORD_RE = re.compile(r"[\w'’]+")

class WordMapper:
    def tokenize(self, line):
        return WORD_RE.findall(line.lower())

    def run(self):
        for line in sys.stdin:
            for word in self.tokenize(line):
                print(f"{word}\t1")

if __name__=="__main__":
    WordMapper().run()
```

정규식에 스마트 따옴표(`’`, U+2019)를 포함시킨 이유는, 전자책 원문이 `don’t`처럼 직선 아포스트로피(`'`)가 아닌 유니코드 스마트 따옴표를 쓰는 경우가 많아, 이를 빠뜨리면 한 단어가 둘로 쪼개지기 때문이다.

### 6.2 Reducer (`scripts/reducer.py`)

정렬되어 들어오는 `단어\t1` 라인들을 단어 단위로 묶어 합산하고, `단어\t총개수`를 출력한다. Hadoop Streaming은 Java API와 달리 `(key, [values])`로 묶어주지 않고 정렬된 라인을 그대로 흘려보내므로, 같은 키가 연속되는 구간을 직접 추적하며 누적한다.

```python
#!/usr/bin/env python3
import sys

class WordReducer:
    def parse(self, line):
        word, count = line.strip().split('\t', 1)
        return (word, int(count))

    def run(self):
        current_word = None
        current_count = 0

        for line in sys.stdin:
            word, count = self.parse(line)

            if word == current_word:
                current_count += count
            else:
                if current_word is not None:
                    print(f"{current_word}\t{current_count}")

                current_word = word
                current_count = count

        if current_word is not None:
            print(f"{current_word}\t{current_count}")

if __name__ == "__main__":
    WordReducer().run()
```

마지막 단어는 루프가 끝난 뒤 별도로 한 번 더 출력해야 하는데, 루프 안에서는 "다음 단어로 넘어갈 때"만 이전 단어를 출력하므로 스트림의 맨 끝에 도달했을 때는 이 로직이 실행되지 않기 때문이다.

<br>

## 7. 컴파일(실행 준비)

Python 스크립트이므로 별도의 컴파일 과정은 없고, 실행 권한만 부여하면 된다.

```bash
chmod +x /scripts/mapper.py /scripts/reducer.py
```

<br>


## 8. 로컬 파이프라인 사전 검증

Hadoop 클러스터에 job을 제출하기 전에, 로직 자체의 정확성을 로컬 파이프로 먼저 검증한다.

```bash
cat /sample/DDIA.txt | python3 /scripts/mapper.py | sort | python3 /scripts/reducer.py > /tmp/local_result.txt
wc -l /tmp/local_result.txt                              # 고유 단어 수 확인
sort -t $'\t' -k2 -nr /tmp/local_result.txt | head -20    # 빈도 상위 단어 확인
```

<br>

## 9. HDFS에 입력 파일 업로드

```bash
hdfs dfs -mkdir -p /user/jurilee/input
hdfs dfs -put /sample/DDIA.txt /user/jurilee/input/
hdfs dfs -ls /user/jurilee/input          # 업로드 결과 확인
hdfs dfs -cat /user/jurilee/input/DDIA.txt | head   # 내용 미리보기
```
<br>

## 10. MapReduce 작업 실행

Hadoop Streaming을 이용해 Python mapper/reducer를 클러스터에 제출한다. `-file` 옵션으로 스크립트를 worker 노드까지 함께 배포한다.

```bash
hadoop jar $HADOOP_HOME/share/hadoop/tools/lib/hadoop-streaming-*.jar \
  -D mapreduce.job.reduces=2 \
  -D mapreduce.input.fileinputformat.split.maxsize=524288 \
  -input /user/jurilee/input/DDIA.txt \
  -output /user/jurilee/output \
  -mapper /scripts/mapper.py \
  -reducer /scripts/reducer.py \
  -combiner /scripts/reducer.py \
  -file /scripts/mapper.py \
  -file /scripts/reducer.py
```

옵션의 의미는 다음과 같다.

| 옵션 | 설명 |
|---|---|
| `mapreduce.job.reduces=2` | reduce task를 2개로 지정해 worker 2대가 나누어 집계하도록 한다 |
| `split.maxsize=524288` | 입력을 512KB 단위로 분할해 mapper task를 여러 개 병렬로 띄운다 (입력 파일이 HDFS 블록 크기보다 작아 기본 설정으로는 split이 1개로만 나뉘기 때문) |
| `-combiner` | mapper 단계에서 부분 합산을 먼저 수행해 reducer로 전송되는 shuffle 데이터량을 줄인다 |
| `-file` | mapper/reducer 스크립트를 클러스터의 모든 노드에 함께 배포한다 |

재실행 시 출력 디렉토리가 이미 존재하면 Hadoop이 실행을 거부하므로, 먼저 삭제한 뒤 다시 제출한다.

```bash
hdfs dfs -rm -r /user/jurilee/output
```

<br>

## 11. 작업 진행 상황 모니터링

- YARN ResourceManager 웹 UI: `http://localhost:8088` — job 진행률과 map/reduce task별 실행 노드(worker1/worker2)를 확인할 수 있다
- HDFS NameNode 웹 UI: `http://localhost:9870` → Utilities → Browse the file system → `/user/jurilee/output`
- CLI: job을 제출한 터미널에 `map 0% reduce 0%`부터 `map 100% reduce 100%`까지 진행률이 실시간으로 출력된다
- 완료된 job의 컨테이너별 실행 노드를 확인하려면 다음 명령을 사용한다.

```bash
yarn logs -applicationId <application_id>
```

<br>

## 12. 결과 파일 검색 및 확인

```bash
hdfs dfs -ls /user/jurilee/output
# _SUCCESS, part-00000, part-00001 (reducer 2개 → 출력 파일 2개)

hdfs dfs -cat /user/jurilee/output/part-00000 /user/jurilee/output/part-00001 > /tmp/hdfs_result.txt
wc -l /tmp/hdfs_result.txt
sort -t $'\t' -k2 -nr /tmp/hdfs_result.txt | head -20
```

출력 파일의 각 줄은 `단어\t개수` 형식이다. 

결과:

```
the     11122
a       6075
to      5757
of      5063
and     5026
in      4445
is      3949
that    2770
for     2288
it      2078
...
```

<br>

### 결과 해석

- **컬럼 의미**: 왼쪽은 소문자로 정규화된 단어, 오른쪽은 전자책 전체에서 그 단어가 등장한 총 횟수다.
- **상위 빈도 단어가 관사/전치사인 것은 정상**: `the`, `a`, `to`, `of`, `and`처럼 의미보다 문법적 역할을 하는 단어가 최상위를 차지하는 건 자연어 텍스트의 일반적인 특성이다 (Zipf 법칙 — 소수의 단어가 전체 출현 횟수의 상당 부분을 차지). 반대로 최상위에 이상한 기호나 코드 조각(`'{`, `0x` 등)이 보인다면 토큰화 정규식에 문제가 있다는 신호로 해석해야 한다.
- **job counter 값 읽는 법** (13번 표 기준):
  - `Map input records` — mapper가 처리한 총 줄(line) 수. 원본 텍스트 파일의 줄 수와 일치해야 한다.
  - `Map output records` — mapper가 만들어낸 `(단어, 1)` 쌍의 총 개수. 곧 전자책 전체의 단어 출현 총 횟수이므로, 사전에 `wc -w`로 확인해둔 값과 비슷한 규모여야 한다.
  - `Combine output records` — combiner가 각 mapper 노드에서 부분 합산을 마친 뒤 남은 `(단어, 부분합)` 쌍의 개수. mapper별로 로컬 집계를 하기 때문에 최종 고유 단어 수보다 크거나 같다.
  - `Reduce output records` — 최종 고유 단어 수. **로컬 파이프라인 결과와 반드시 일치해야 하는 값**이며, 다르면 로직에 문제가 있다는 뜻이다.

<br>

## 13. 결과 검증

로컬 파이프라인 결과(`/tmp/local_result.txt`)와 HDFS 최종 결과(`/tmp/hdfs_result.txt`)의 고유 단어 수를 비교해 두 결과가 일치함을 확인했다.

| 항목 | 값 |
|---|---|
| 로컬 파이프라인 고유 단어 수 | 11704 |
| HDFS 출력 고유 단어 수 | 11704 (일치) |
| Map input records | 24098 |
| Map output records | 229816 |
| Combine output records | 16730 |
| Launched map task 수 | 2 |
| Launched reduce task 수 | 2 |

<br>

## 14. 실행 결과 요약

- worker 2대 클러스터에서 map task 2개, reduce task 2개가 병렬로 실행됐다 (ApplicationMaster는 worker2에서 구동됨)
- combiner를 통해 shuffle 데이터량을 22만 건에서 1.6만 건 수준으로 줄였다
- job은 에러 없이 `Job completed successfully`로 완료됐다
- 클러스터 실행 결과가 로컬 검증 결과와 정확히 일치해 정확성을 확인했다
