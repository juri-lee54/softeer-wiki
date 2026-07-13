# Docker 기반 단일 노드(Single-node) Hadoop 클러스터

Docker 컨테이너 하나로 동작하는 단일 노드 Hadoop(HDFS + YARN) 클러스터입니다.

## 구성 파일
```
hadoop-docker/
├── Dockerfile
├── entrypoint.sh
└── config/
    ├── core-site.xml
    ├── hdfs-site.xml
    ├── mapred-site.xml
    └── yarn-site.xml
```

## 사전 준비
- Docker Desktop(Mac/Windows) 또는 Docker Engine(Linux)이 설치되어 있어야 합니다.
- `docker --version` 명령으로 설치 여부를 확인하세요.

---

## 1. 이미지 빌드

`hadoop-docker` 디렉토리로 이동한 뒤 아래 명령을 실행합니다.

```bash
cd hadoop-docker
docker build -t w3m1 .
```

빌드 과정에서 Apache 공식 미러에서 Hadoop 3.3.6 바이너리를 다운로드하므로 몇 분 정도 소요될 수 있습니다.
설정 파일이나 스크립트를 수정한 뒤에는 캐시 문제를 피하기 위해 아래처럼 캐시 없이 재빌드하는 것을 권장합니다.
```bash
docker build --no-cache -t w3m1 .
```

---

## 2. 컨테이너 실행 (데이터 영속화 포함)

호스트에 데이터를 영속화하기 위해 로컬 디렉토리를 볼륨으로 마운트합니다.

```bash
# 데이터를 저장할 로컬 디렉토리 생성
mkdir -p ~/hadoop-data/name ~/hadoop-data/data

docker run -d \
  --name w3m1 \
  -p 9870:9870 \
  -p 9000:9000 \
  -p 8088:8088 \
  -p 9864:9864 \
  -p 9866:9866 \
  -p 8042:8042 \
  -v ~/hadoop-data/name:/hadoop/dfs/name \
  -v ~/hadoop-data/data:/hadoop/dfs/data \
  w3m1
```

- `-v ~/hadoop-data/name:/hadoop/dfs/name` : 네임노드 메타데이터 영속화
- `-v ~/hadoop-data/data:/hadoop/dfs/data` : 데이터노드 블록 데이터 영속화
- 이렇게 마운트해두면 컨테이너를 `docker stop` / `docker rm` 한 뒤 다시 만들어도 HDFS에 저장한 파일이 그대로 남아 있습니다.

컨테이너가 정상적으로 떴는지 확인:
```bash
docker logs -f w3m1
```
아래 메시지들이 순서대로 뜨면 정상 기동된 것입니다.
```
>>> NameNode가 아직 포맷되지 않았습니다. 포맷을 진행합니다...  (최초 실행 시)
>>> Hadoop 서비스가 시작되었습니다.
>>> HDFS Web UI : http://localhost:9870
>>> YARN Web UI : http://localhost:8088
```

컨테이너 내부에서 데몬이 모두 떠 있는지 직접 확인하려면:
```bash
docker exec -it w3m1 jps
```
`NameNode`, `DataNode`, `SecondaryNameNode`, `ResourceManager`, `NodeManager` 5개가 모두 보여야 합니다.

---

## 3. HDFS 웹 UI 접속

호스트 브라우저에서 아래 주소로 접속합니다.
- HDFS NameNode UI: http://localhost:9870
- YARN ResourceManager UI: http://localhost:8088

> **참고 (Mac 환경)**: Docker Desktop for Mac 환경에 따라 `localhost:8088`(YARN UI) 접속 시 간헐적으로 `Connection reset by peer`가 발생할 수 있습니다. 이 경우 `http://127.0.0.1:8088`로 시도하거나 Docker Desktop을 재시작해보세요. 이 미션의 핵심 요구사항은 **HDFS 웹 UI(9870)** 이므로, YARN UI(8088) 접속이 안 되더라도 미션 진행에는 지장이 없습니다.

---

## 4. HDFS 기본 조작 (컨테이너 내부에서 실행)

컨테이너 안으로 접속:
```bash
docker exec -it w3m1 bash
```

### 4-1. 디렉토리 생성
```bash
hdfs dfs -mkdir -p /user/root/mydata
```

### 4-2. 로컬 파일을 HDFS로 업로드
```bash
echo "Hello, Hadoop! This is a test file." > /tmp/sample.txt
hdfs dfs -put /tmp/sample.txt /user/root/mydata/sample.txt
```

### 4-3. 업로드된 파일 확인
```bash
hdfs dfs -ls /user/root/mydata
```

### 4-4. HDFS에서 파일 내용 바로 확인
```bash
hdfs dfs -cat /user/root/mydata/sample.txt
```

### 4-5. HDFS 파일을 로컬로 다시 내려받기
```bash
hdfs dfs -get /user/root/mydata/sample.txt /tmp/downloaded_sample.txt
cat /tmp/downloaded_sample.txt
```
`/tmp/sample.txt` 와 `/tmp/downloaded_sample.txt` 의 내용이 동일하면 업로드/다운로드가 정상적으로 검증된 것입니다.

---

## 5. 데이터 영속성(Persistence) 검증 방법

1. 위 4번 과정으로 `/user/root/mydata/sample.txt` 를 만들어 둡니다.
2. 컨테이너를 중지 후 삭제합니다. (이미지는 삭제하지 않습니다.)
   ```bash
   docker stop w3m1
   docker rm w3m1
   ```
3. 2번의 `docker run` 명령을 (동일한 `-v` 볼륨 경로로) 다시 실행합니다.
4. 로그에서 재포맷이 아니라 아래 메시지가 뜨는지 확인합니다.
   ```
   >>> 기존 NameNode 데이터가 발견되었습니다. 포맷을 건너뜁니다.
   ```
5. 데몬이 다 뜬 뒤, 파일이 그대로 남아 있는지 확인합니다.
   ```bash
   docker exec -it w3m1 hdfs dfs -cat /user/root/mydata/sample.txt
   ```
   `Hello, Hadoop! This is a test file.` 가 다시 출력되면, 컨테이너를 완전히 삭제했다 재생성해도 HDFS 데이터가 보존된다는 것이 증명된 것입니다.

`entrypoint.sh`는 `/hadoop/dfs/name/current` 디렉토리가 이미 존재하면 네임노드를 재포맷하지 않으므로, 볼륨에 저장된 메타데이터와 블록 데이터가 그대로 복원됩니다.

---

## 6. 컨테이너 중지 / 재시작 / 삭제

```bash
docker stop w3m1      # 중지
docker start w3m1     # 재시작 (기존 데이터 유지)
docker rm -f w3m1      # 완전 삭제 (볼륨은 호스트에 남음)
```

---

## 7. 동작 방식 참고 (SSH 대신 로컬 데몬 직접 실행)

이 구성은 Hadoop의 `start-dfs.sh` / `start-yarn.sh`(내부적으로 SSH·pdsh를 통해 원격 접속하는 방식) 대신, `entrypoint.sh`에서 각 데몬을 아래처럼 **SSH를 거치지 않고 로컬에서 직접** 실행합니다.

```bash
hdfs --daemon start namenode
hdfs --daemon start datanode
hdfs --daemon start secondarynamenode
yarn --daemon start resourcemanager
yarn --daemon start nodemanager
```

단일 노드 환경에서는 서버가 1대뿐이라 원격 접속(SSH) 자체가 불필요한 우회 경로이며, 이 방식이 Docker Desktop 환경에서 훨씬 안정적으로 동작합니다. (SSH 기반 방식은 컨테이너 환경에 따라 `Connection refused` 등 간헐적인 접속 실패가 발생할 수 있습니다.)
