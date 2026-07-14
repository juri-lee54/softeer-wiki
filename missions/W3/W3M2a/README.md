# Docker 기반 멀티노드(Multi-node) Hadoop 클러스터

Docker Compose로 master 1대 + worker 2대(worker1, worker2)를 띄우는 멀티노드 Hadoop(HDFS + YARN) 클러스터다.
같은 이미지를 모든 노드에서 재사용하고, `HADOOP_NODE_TYPE` 환경변수로 master/worker 역할만 다르게 동작한다.
master는 ssh로 각 worker에 접속해 DataNode/NodeManager를 원격으로 띄운다. ([W3M1](../W3M1)의 단일 노드 SSH 실행 방식을 그대로 확장한 구성이다.)

## 구성 파일
```
W3M2a/
├── Dockerfile
├── docker-compose.yml
├── entrypoint.sh
├── sample/
│   └── wordcount_input.txt
└── config/
    ├── core-site.xml
    ├── hdfs-site.xml
    ├── mapred-site.xml
    ├── yarn-site.xml
    └── workers
```

## 사전 준비
- Docker Desktop(Mac/Windows) 또는 Docker Engine(Linux)이 설치되어 있어야 한다.
- `docker --version`, `docker compose version` 명령으로 설치 여부를 확인한다.

---

## 1. Docker 이미지 빌드 방법

`W3M2a` 디렉토리로 이동한 뒤 아래 명령을 실행한다.

```bash
cd W3M2a
docker compose build
```

- master, worker1, worker2 세 서비스가 모두 같은 `Dockerfile`을 사용하며, 빌드 결과는 `hadoop-cluster:latest` 이미지 하나로 공유된다.
- 빌드 과정에서 Apache 공식 미러에서 Hadoop 3.3.6 바이너리를 다운로드하므로 몇 분 정도 소요될 수 있다.
- 설정 파일이나 스크립트를 수정한 뒤에는 캐시 문제를 피하기 위해 아래처럼 캐시 없이 재빌드하는 것을 권장한다.
  ```bash
  docker compose build --no-cache
  ```
- (참고) 세 서비스가 같은 이미지 태그를 동시에 빌드하다 보니 `docker compose build`가 `already exists` 경고와 함께 일부 서비스에서 실패로 표시될 수 있다. 이미지 자체는 정상적으로 생성되므로 무시해도 되고, 신경 쓰이면 `docker compose build` 이후 `docker images hadoop-cluster:latest`로 이미지가 만들어졌는지만 확인하면 된다.

---

## 2. 컨테이너 실행 방법

```bash
docker compose up -d
```

- `master`, `worker1`, `worker2` 컨테이너가 `hadoop-net`이라는 같은 Docker 브리지 네트워크에 연결되어 서로 호스트 이름(`master`, `worker1`, `worker2`)으로 통신한다.
- 각 컨테이너 시작 시 `entrypoint.sh`가 실행되어 sshd를 띄우고, master는 자신과 모든 worker의 SSH가 준비될 때까지 기다린 뒤 HDFS/YARN 데몬을 자동으로 띄운다. worker는 sshd만 띄운 채 master의 ssh 접속을 기다린다.

컨테이너가 정상적으로 떴는지 로그로 확인한다.
```bash
docker logs -f master
```
아래와 같은 메시지가 순서대로 뜨면 정상 기동된 것이다.
```
>>> worker1:22 가 뜨기를 기다리는 중...
>>> worker1:22 준비 완료.
>>> worker2:22 준비 완료.
>>> NameNode가 아직 포맷되지 않았습니다. 포맷을 진행합니다...  (최초 실행 시)
Starting namenodes on [master]
Starting datanodes
Starting secondary namenodes [master]
Starting resourcemanager
Starting nodemanagers
>>> Hadoop 서비스가 시작되었습니다.
>>> HDFS Web UI : http://localhost:9870
>>> YARN Web UI : http://localhost:8088
```

각 노드에서 데몬이 정상적으로 떠 있는지 확인한다.
```bash
docker exec master  jps   # NameNode, SecondaryNameNode, ResourceManager
docker exec worker1 jps   # DataNode, NodeManager
docker exec worker2 jps   # DataNode, NodeManager
```

컨테이너 중지 / 재시작 / 삭제:
```bash
docker compose stop      # 중지 (데이터 유지)
docker compose start     # 재시작 (기존 데이터 유지)
docker compose down      # 컨테이너/네트워크 삭제 (볼륨은 호스트에 남음)
```

---

## 3. Hadoop 설정 방법

`config/` 아래 파일들이 빌드 시 `Dockerfile`의 `COPY`로 이미지 안 `$HADOOP_CONF_DIR`(`/opt/hadoop/etc/hadoop`)에 복사된다.

| 파일 | 역할 | 이 프로젝트의 주요 설정 |
| --- | --- | --- |
| `core-site.xml` | Hadoop 공통 설정 | `fs.defaultFS=hdfs://master:9000` |
| `hdfs-site.xml` | HDFS 설정 | `dfs.replication=2`(worker가 2대라 복제본 2개), `dfs.namenode.http-address=master:9870`, `dfs.namenode.secondary.http-address=master:9868`, `dfs.permissions.enabled=false` |
| `mapred-site.xml` | MapReduce 설정 | `mapreduce.framework.name=yarn`, Map/Reduce/AppMaster 메모리 512MB |
| `yarn-site.xml` | YARN 설정 | `yarn.resourcemanager.hostname=master`, `yarn.nodemanager.aux-services=mapreduce_shuffle`, NodeManager 메모리 2048MB/2vcore |
| `workers` | master가 ssh로 DataNode/NodeManager를 띄울 worker 목록 | `worker1`, `worker2` |

노드별 사용자/환경변수(`JAVA_HOME`, `HDFS_*_USER`, `YARN_*_USER`, `HADOOP_SSH_OPTS` 등)는 `Dockerfile`의 `ENV`와, ssh 세션에서도 적용되도록 `hadoop-env.sh`에 추가한 `export` 구문으로 관리한다.

설정을 바꾸는 방법은 다음과 같다.
1. `config/` 아래 해당 파일을 수정한다. (예: worker를 늘리려면 `config/workers`에 호스트를 추가하고, `docker-compose.yml`에 서비스를 추가하고, `dfs.replication` 값도 함께 조정)
2. `docker compose build --no-cache`로 이미지를 다시 빌드한다.
3. `docker compose up -d`로 다시 띄운다. `-v` 볼륨 경로가 같다면 기존 HDFS 데이터는 유지된다.

---

## 4. HDFS 사용 방법

### 4-1. 웹 UI 접속
호스트 브라우저에서 아래 주소로 접속한다.
- HDFS NameNode UI: http://localhost:9870 (Datanodes 메뉴에서 worker1, worker2 2대가 보여야 한다)
- YARN ResourceManager UI: http://localhost:8088 (Nodes 메뉴에서 worker1, worker2의 NodeManager 2대가 보여야 한다)

### 4-2. 명령어로 HDFS 조작하기 (master 컨테이너 안에서 실행)
```bash
docker exec -it master bash
```

디렉토리 생성:
```bash
hdfs dfs -mkdir -p /user/root/input
```

파일 목록 확인:
```bash
hdfs dfs -ls /user/root/input
```

파일 내용 바로 확인:
```bash
hdfs dfs -cat /user/root/input/wordcount_input.txt
```

---

## 5. 파일 업로드 및 다운로드 방법

`sample/wordcount_input.txt`는 `docker-compose.yml`에 의해 master 컨테이너의 `/sample`에 마운트되어 있어 바로 업로드할 수 있다.

### 5-1. 로컬 파일을 HDFS로 업로드
```bash
docker exec master hdfs dfs -mkdir -p /user/root/input
docker exec master hdfs dfs -put -f /sample/wordcount_input.txt /user/root/input/
docker exec master hdfs dfs -ls /user/root/input
```

### 5-2. HDFS 파일을 로컬로 다시 내려받기
```bash
docker exec master hdfs dfs -get /user/root/input/wordcount_input.txt /tmp/downloaded.txt
docker exec master cat /tmp/downloaded.txt
```

### 5-3. 샘플 MapReduce(WordCount) 작업 실행
호스트 셸(zsh/bash)에서 `$HADOOP_HOME`이나 `*` 와일드카드가 로컬에서 먼저 해석되지 않도록, 명령 전체를 따옴표로 묶어 컨테이너 안의 bash가 처리하게 한다.
```bash
docker exec master bash -c 'yarn jar $HADOOP_HOME/share/hadoop/mapreduce/hadoop-mapreduce-examples-*.jar wordcount /user/root/input /user/root/output'
```
작업이 끝나면 결과를 확인한다.
```bash
docker exec master hdfs dfs -cat /user/root/output/part-r-00000
```
- 실행 중 http://localhost:8088 에서 Job 진행 상황을, Job 상세 화면에서 어떤 노드(worker1/worker2)가 map/reduce task를 처리했는지 확인할 수 있다.
- 이미 `/user/root/output`이 있으면 `hdfs dfs -rm -r /user/root/output`으로 지운 뒤 다시 실행한다. (MapReduce는 출력 디렉토리가 미리 존재하면 실패한다.)

### 5-4. 데이터 영속성(Persistence) 검증
1. 위 5-1, 5-3 과정으로 `/user/root/input`, `/user/root/output`을 만들어 둔다.
2. 클러스터를 완전히 내렸다가 다시 올린다.
   ```bash
   docker compose down
   docker compose up -d
   ```
3. `docker logs master`에서 재포맷이 아니라 아래 메시지가 뜨는지 확인한다.
   ```
   >>> 기존 NameNode 데이터가 발견되었습니다. 포맷을 건너뜁니다.
   ```
4. 데몬이 다 뜬 뒤, 파일과 MapReduce 결과가 그대로 남아 있는지 확인한다.
   ```bash
   docker exec master hdfs dfs -cat /user/root/output/part-r-00000
   docker exec master hdfs dfsadmin -report   # Live datanodes (2) 확인
   ```
   `docker-compose.yml`에서 `master`는 `./data/master/name`, `worker1`/`worker2`는 각각 `./data/worker1/data`, `./data/worker2/data`를 호스트에 마운트하므로, 컨테이너를 지웠다 다시 만들어도 NameNode 메타데이터와 DataNode 블록 데이터가 그대로 복원된다.

---

## 6. 동작 방식 참고 (SSH 기반 멀티노드 데몬 실행)

`entrypoint.sh`는 `HADOOP_NODE_TYPE`(docker-compose.yml에서 주입)에 따라 역할을 나눈다.

- **master**: 자기 자신과 `config/workers`(`worker1`, `worker2`)의 sshd가 뜰 때까지 기다린 뒤, 최초 1회만 NameNode를 포맷하고 `start-dfs.sh` / `start-yarn.sh`를 실행한다. 이 스크립트들은 내부적으로 `ssh worker1`, `ssh worker2`로 접속해 각 worker에서 DataNode/NodeManager를 띄운다.
- **worker**: sshd만 띄운 채 master의 ssh 접속을 기다린다. 데몬은 master가 원격으로 띄워준다.

이를 위해 Dockerfile 빌드 시점에 다음을 준비해둔다.
- `openssh-server`/`openssh-client` 설치, sshd 호스트 키 생성
- 비밀번호 없이 root로 접속 가능하도록 `id_rsa`/`authorized_keys` 생성 (모든 노드가 같은 이미지이므로 키가 공유되어 master → worker 무인증 ssh 접속이 가능함)
- `PermitRootLogin yes`, `PubkeyAuthentication yes`, `PasswordAuthentication no`, `~/.ssh/config`의 `StrictHostKeyChecking no` 설정으로 최초 접속 시 프롬프트 없이 자동 접속

> 참고: `docker logs master`에 SSH 대기 메시지가 오래 반복되면 `docker compose ps`로 worker 컨테이너가 실제로 떠 있는지, `docker logs worker1`/`worker2`에 오류가 없는지 먼저 확인한다.
