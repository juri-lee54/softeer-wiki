# W3M2b : Docker 기반 멀티노드(Multi-node) Hadoop 클러스터

Docker Compose로 master 1대 + worker 2대(worker1, worker2)를 띄우는 멀티노드 Hadoop(HDFS + YARN) 클러스터다.
같은 이미지를 모든 노드에서 재사용하고, `HADOOP_NODE_TYPE` 환경변수로 master/worker 역할만 다르게 동작한다.
master는 ssh로 각 worker에 접속해 DataNode/NodeManager를 원격으로 띄운다. ([W3M1](../W3M1)의 단일 노드 SSH 실행 방식을 그대로 확장한 ([W3M2](../W3M2A)에 modify, verigy 스크립트를 추가했다.)

## 구성 파일
먼저 아래의 코드로 docker image와 container를 만들었다.
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

### 제출 파일 구조
제출 파일 구조는 다음과 같다

```
W3M2b/
├── Dockerfile                 # python3 포함 (수정 스크립트 실행용)
├── docker-compose.yml         # master에 namenode alias, scripts/ 볼륨 마운트 추가
├── entrypoint.sh
├── README.md
├── config/                    # 이미지 빌드에 쓰이는 원본 설정 (기존 W3M2a 값 그대로)
├── scripts/
│   ├── modify_config.py       # 제출 스크립트 1: 구성 수정
│   └── verify_config.py       # 제출 스크립트 2: 구성 검증
├── config_submission/
│   ├── original/              # 원본 4개 설정 파일
│   ├── modified/              # modify_config.py가 실제로 수정한 결과 (컨테이너에서 추출)
│   └── script_backups/        # modify_config.py가 만든 .bak 백업 파일 (백업 동작 증거)
└── sample/
    └── wordcount_input.txt
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

---

## 7. 구성 자동 수정 스크립트 (`scripts/modify_config.py`)

W3M2b 과제 요구사항에 맞춰, 하둡 설정 12개 항목을 자동으로 백업 → 수정 → (필요 시) 워커 동기화 → 서비스 재시작까지 처리하는 파이썬 스크립트다. 

`docker-compose.yml`에서 `./scripts:/scripts`로 master 컨테이너에 마운트되어 있어서, 호스트에서 이 파일을 수정하면 재빌드 없이 바로 컨테이너 안에 반영된다.

### 무엇을 바꾸는가

| 파일 | 설정 키 | 값 |
| --- | --- | --- |
| core-site.xml | `fs.defaultFS` | `hdfs://namenode:9000` |
| core-site.xml | `hadoop.tmp.dir` | `/hadoop/tmp` |
| core-site.xml | `io.file.buffer.size` | `131072` |
| hdfs-site.xml | `dfs.replication` | `2` |
| hdfs-site.xml | `dfs.blocksize` | `134217728` |
| hdfs-site.xml | `dfs.namenode.name.dir` | `/hadoop/dfs/name` |
| mapred-site.xml | `mapreduce.framework.name` | `yarn` |
| mapred-site.xml | `mapreduce.jobhistory.address` | `namenode:10020` |
| mapred-site.xml | `mapreduce.task.io.sort.mb` | `256` |
| yarn-site.xml | `yarn.resourcemanager.address` | `namenode:8032` |
| yarn-site.xml | `yarn.nodemanager.resource.memory-mb` | `8192` |
| yarn-site.xml | `yarn.scheduler.minimum-allocation-mb` | `1024` |

`fs.defaultFS`, `mapreduce.jobhistory.address`, `yarn.resourcemanager.address`가 `master`가 아니라 `namenode`라는 호스트명을 쓰기 때문에, `docker-compose.yml`의 master 서비스에 `aliases: [master, namenode]`를 추가해서 같은 컨테이너가 `namenode`로도 resolve되도록 해뒀다 (자세한 내용은 [9. 트러블슈팅](#9-트러블슈팅--겪은-이슈와-해결) 참고).

### 실행 방법

```bash
docker exec master python3 /scripts/modify_config.py /opt/hadoop/etc/hadoop
```

인자로 하둡 설정 디렉토리(`$HADOOP_CONF_DIR`) 경로를 받는다.

### 동작 순서

1. **백업**: 각 설정 파일을 수정하기 전에 같은 디렉토리에 `<파일명>.bak.<타임스탬프>`로 복사해둔다 (`backup_file`).
2. **수정**: `xml.etree.ElementTree`로 파싱해서, 해당 `<name>`을 가진 `<property>`를 찾아 `<value>`만 바꾸고, 없으면 새 `<property>`를 만들어 추가한다 (`set_property`).
3. **워커 동기화**: `config/workers` 파일에 적힌 호스트 목록(`worker1`, `worker2`)을 읽어서, 수정된 4개 파일을 `scp`로 각 워커에도 복사한다 (`sync_to_workers`). worker1/worker2는 master와 별도의 컨테이너라 이미지 빌드 시점의 설정만 갖고 있어서, 이 단계가 없으면 master만 새 설정을 갖고 워커는 예전 값 그대로 남는다.
4. **서비스 재시작**: `stop-dfs.sh` → `stop-yarn.sh` → `start-dfs.sh` → `start-yarn.sh` 순서로 재시작한다 (`restart_hadoop`).
5. 각 단계 실패 시 원인을 출력하고, 전체가 성공했을 때만 `Configuration changes applied and services restarted.`를 출력하며 종료코드 0으로 끝난다.

### 예상 출력

```
Backing up core-site.xml...
Modifying core-site.xml...
Backing up hdfs-site.xml...
Modifying hdfs-site.xml...
Backing up mapred-site.xml...
Modifying mapred-site.xml...
Backing up yarn-site.xml...
Modifying yarn-site.xml...
Syncing config to worker1...
Syncing config to worker2...
Stopping Hadoop DFS...
Stopping YARN...
Starting Hadoop DFS...
Starting YARN...
Configuration changes applied and services restarted.
```

---

## 8. 구성 검증 스크립트 (`scripts/verify_config.py`)

`modify_config.py`가 적용한 설정이 실제로 클러스터에 반영됐는지 하둡 명령어와 YARN REST API로 확인하는 스크립트다. 마찬가지로 `/scripts`에 마운트되어 있다.

### 실행 방법

```bash
docker exec master python3 /scripts/verify_config.py
```

별도 인자는 필요 없다 (살아있는 클러스터에 직접 명령을 실행해서 확인하기 때문).

### 확인하는 항목

1. **설정값 12개**: `hdfs getconf -confKey <key>`로 core/hdfs/mapred/yarn의 12개 설정을 전부 조회해서 기대값과 비교.
   - 이 Hadoop 버전(3.3.6)에는 `hadoop getconf`, `yarn getconf` 서브커맨드가 존재하지 않는다(`ERROR: getconf is not COMMAND`). `hdfs getconf -confKey`가 core/hdfs/mapred/yarn 설정을 전부 읽어올 수 있어서, 12개 항목 모두 `hdfs` 명령으로 조회한다.
2. **HDFS 복제 계수**: 테스트 파일을 HDFS에 업로드한 뒤 `hdfs dfs -stat %r`로 실제 복제본 개수(2)를 확인.
3. **MapReduce + YARN**: `wordcount` 예제 잡을 실행해서 YARN 위에서 정상적으로 끝나는지 확인.
4. **YARN 총 메모리**: ResourceManager REST API(`http://master:8088/ws/v1/cluster/metrics`)를 호출해서 `totalMB`(예상: 8192MB × 2노드 = 16384MB)와 `totalNodes`(예상: 2)를 확인.
5. HDFS 관련 체크 전에 `hdfs dfsadmin -safemode wait`로 NameNode가 safe mode를 벗어날 때까지 기다린다 — `modify_config.py`로 막 재시작한 직후에 바로 검증 스크립트를 돌리면 NameNode가 safe mode라 쓰기가 막혀 있기 때문.

### 예상 출력

```
PASS: ['hdfs', 'getconf', '-confKey', 'fs.defaultFS'] -> hdfs://namenode:9000
PASS: ['hdfs', 'getconf', '-confKey', 'hadoop.tmp.dir'] -> /hadoop/tmp
PASS: ['hdfs', 'getconf', '-confKey', 'io.file.buffer.size'] -> 131072
PASS: ['hdfs', 'getconf', '-confKey', 'dfs.replication'] -> 2
PASS: ['hdfs', 'getconf', '-confKey', 'dfs.blocksize'] -> 134217728
PASS: ['hdfs', 'getconf', '-confKey', 'dfs.namenode.name.dir'] -> /hadoop/dfs/name
PASS: ['hdfs', 'getconf', '-confKey', 'mapreduce.framework.name'] -> yarn
PASS: ['hdfs', 'getconf', '-confKey', 'mapreduce.jobhistory.address'] -> namenode:10020
PASS: ['hdfs', 'getconf', '-confKey', 'mapreduce.task.io.sort.mb'] -> 256
PASS: ['hdfs', 'getconf', '-confKey', 'yarn.resourcemanager.address'] -> namenode:8032
PASS: ['hdfs', 'getconf', '-confKey', 'yarn.nodemanager.resource.memory-mb'] -> 8192
PASS: ['hdfs', 'getconf', '-confKey', 'yarn.scheduler.minimum-allocation-mb'] -> 1024
Waiting for NameNode to leave safe mode...
PASS: Replication factor is 2
PASS: MapReduce wordcount job completed successfully using YARN
PASS: YARN total memory is 16384MB across 2 nodes

15/15 checks passed
```

설정값이 기대값과 다르면 아래처럼 실제 값과 함께 FAIL이 출력된다.
```
FAIL: ['hdfs', 'getconf', '-confKey', 'fs.defaultFS'] -> hdfs://namenode:8020 (expected hdfs://namenode:9000)
```

---

## 9. 트러블슈팅 — 겪은 이슈와 해결

### 9-1. `namenode` 호스트를 resolve하지 못함

`fs.defaultFS`를 `hdfs://namenode:9000`으로 바꾼 뒤 `modify_config.py`가 하둡 서비스를 재시작하니 아래 에러가 났다.
```
Stopping namenodes on [namenode]
namenode: ssh: Could not resolve hostname namenode: Name or service not known
```
`start-dfs.sh`는 `fs.defaultFS`에서 호스트명을 뽑아 그 호스트에 ssh로 접속해 NameNode를 띄우는데, 도커 네트워크 안에는 `master`, `worker1`, `worker2`라는 이름만 있고 `namenode`는 없었기 때문이다. `docker-compose.yml`의 master 서비스 네트워크 alias에 `namenode`를 추가해서 해결했다:
```yaml
networks:
  hadoop-net:
    aliases: [master, namenode]
```
같은 컨테이너가 `master`(기존 hdfs-site.xml/yarn-site.xml의 다른 설정들이 참조)와 `namenode`(이번에 새로 바꾼 설정들이 참조) 양쪽 이름으로 모두 resolve되게 만드는 방식이다.

### 9-2. worker1/worker2에 설정이 반영되지 않음

`modify_config.py`가 master 컨테이너의 `$HADOOP_CONF_DIR`만 수정하다 보니, master는 `yarn.nodemanager.resource.memory-mb=8192`를 갖고 있어도 worker1/worker2는 이미지 빌드 시점의 예전 값(`2048`)을 그대로 갖고 있었다. 그 결과 YARN 총 메모리가 8192×2가 아니라 2048×2로 조회됐다. worker1/worker2는 master와 완전히 독립된 컨테이너라 파일시스템이 공유되지 않기 때문에 생긴 문제로, `modify_config.py`에 `config/workers`를 읽어 각 워커에 `scp`로 설정 파일을 동기화하는 `sync_to_workers` 단계를 추가해서 해결했다.

### 9-3. 재시작 직후 검증하면 "Name node is in safe mode" 에러

`modify_config.py`로 서비스를 재시작한 직후 곧바로 `verify_config.py`를 돌리면, NameNode가 아직 DataNode들의 블록 리포트를 다 받지 못해 safe mode 상태라 HDFS 쓰기(`hdfs dfs -put`)와 MapReduce 잡이 모두 실패했다. `verify_config.py`에 `hdfs dfsadmin -safemode wait`로 safe mode가 풀릴 때까지 대기하는 단계를 추가해서 해결했다.

### 9-4. 미션 예시 출력과 실제 요구사항의 불일치 (`mapreduce.job.tracker`)

과제 설명의 "검증 스크립트 예상 출력" 예시에는 `mapreduce.job.tracker -> namenode:9001`이 있지만, 정작 "기능요구사항"에는 `mapreduce.jobhistory.address`를 `namenode:10020`으로 바꾸라고 되어 있을 뿐 `mapreduce.job.tracker`는 언급되지 않는다. 실제로 클러스터에 조회해보면:
```
$ hdfs getconf -confKey mapreduce.job.tracker
Configuration mapreduce.job.tracker is missing.
```
`mapreduce.job.tracker`는 MapReduce v1(JobTracker) 시절의 프로퍼티로, `mapreduce.framework.name=yarn`으로 동작하는 이 클러스터에는 애초에 존재하지 않는 설정이다. 이는 과제 설명 자체의 템플릿 잔재로 판단해, `verify_config.py`는 실제 기능요구사항에 명시된 `mapreduce.jobhistory.address`를 검증하도록 구현했다.

---

