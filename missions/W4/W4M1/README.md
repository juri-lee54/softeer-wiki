# Spark Standalone Cluster on Docker

Docker로 Apache Spark 독립형(standalone) 클러스터(마스터 1 + 워커 2)를 구성하고,
몬테카를로 방식으로 π를 추정하는 Spark 작업을 실행하는 프로젝트다.

## 디렉토리 구조

```
W4M1/
├── Dockerfile          # Spark 노드(마스터/워커 공용) 이미지 정의
├── entrypoint.sh        # SPARK_MODE(master/worker)에 따라 실행할 프로세스 분기
├── docker-compose.yml   # 마스터 1 + 워커 2 클러스터 구성
├── submit.sh            # spark-submit으로 작업 제출하는 스크립트
├── jobs/
│   └── pi.py             # π 추정 Spark 작업 (입력 CSV를 읽어 파티션 설정을 가져옴)
├── data/
│   └── pi_config.csv     # 작업 입력 데이터셋 (파티션 수 / 파티션당 샘플 수)
└── output/               # 작업 결과 CSV가 저장되는 위치 (최초 실행 후 생성됨)
```

## 사전 준비

- Docker Desktop이 설치되어 있고 실행 중이어야 한다
- 이 저장소를 로컬에 clone/다운로드한다

## 1. 이미지 빌드 + 클러스터 기동

```bash
cd DE/missions/W4/W4M1
docker-compose up --build -d
```

- 최초 빌드 시 Spark 배포판(약 500MB)을 다운로드하므로 몇 분 걸릴 수 있다
- `-d`는 백그라운드 실행 옵션이다

## 2. 클러스터 상태 확인

```bash
docker-compose ps
```

`spark-master`, `spark-worker-1`, `spark-worker-2` 세 컨테이너가 모두 `Up` 상태인지 확인한다.

브라우저에서 아래 URL로 접속해 워커 2개가 정상 등록됐는지 확인한다.

- 마스터 웹 UI: http://localhost:8080 (Workers 섹션에 2개 등록되어 있어야 함)
- 워커 1 웹 UI: http://localhost:8081
- 워커 2 웹 UI: http://localhost:8082

여기서 워커가 안 보이면 마스터 URL/네트워크 설정을 확인한다.

## 3. 작업 제출

```bash
chmod +x submit.sh
```

```bash
./submit.sh
```

기본적으로 `data/pi_config.csv`를 입력으로 읽고, 결과를 `output/pi_result/`에 저장한다.
입력/출력 경로를 바꾸고 싶다면 인자로 전달한다 (둘 다 컨테이너 내부 기준 경로).

```bash
./submit.sh /opt/data/pi_config.csv /opt/output/pi_result
```

## 4. 결과 확인

터미널 로그에 다음과 같은 라인이 출력된다.

```
Pi is roughly 3.141592
```

출력 파일은 볼륨 마운트를 통해 호스트에서 바로 확인 가능하다.

```bash
ls output/pi_result/
cat output/pi_result/part-*.csv
```

워커 수(2개)만큼 파티션이 나뉘어 `part-00000`, `part-00001` 두 개의 결과 파일이 생성되며,
각 파일에는 `partition_id`, 해당 파티션에서 처리한 `num_samples`, 원 안에 들어간 `num_hits`가 담겨 있다.

Spark 웹 UI(http://localhost:8080)의 `Completed Applications`에서도 작업 실행 이력을 확인할 수 있다.

## 5. 로그 / 디버깅

```bash
docker logs spark-master
docker logs spark-worker-1
docker logs spark-worker-2
```

- 워커가 마스터에 접속하지 못하면 `spark-worker-*` 로그에 연결 재시도 메시지가 반복된다.
  이 경우 `docker-compose.yml`의 `SPARK_MASTER_URL` 값과 마스터 컨테이너 상태를 확인한다.
- `entrypoint.sh`는 `SPARK_MODE` 값이 `master`/`worker`가 아니면 에러 메시지를 출력하고 종료한다.

## 6. 정리

```bash
docker-compose down
```

## 입력 데이터셋 설정 변경

`data/pi_config.csv`에서 파티션 수와 파티션당 샘플 수를 조절할 수 있다.

```csv
partitions,samples_per_partition
2,1000000
```

파티션 수는 워커 수(2)에 맞추는 것을 권장한다. 파티션 수가 데이터 양보다 많으면
일부 파티션이 비어 빈 결과 파일이 생길 수 있다.
