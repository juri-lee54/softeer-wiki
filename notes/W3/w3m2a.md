# 목차
- [목차](#목차)
- [미션 설명](#미션-설명)
- [W3M1과 겹치는 개념](#w3m1과-겹치는-개념)
- [멀티노드에서 새로 등장하는 개념](#멀티노드에서-새로-등장하는-개념)

<br>
<br>

# 미션 설명

[w3m1](./w3m1.md)이 "컨테이너 1개 안에 가짜로 여러 데몬을 흉내 낸 pseudo-distributed 모드"였다면,
w3m2a는 **컨테이너 3개(master, worker1, worker2)를 실제로 띄워서 서로 네트워크로 통신하는 분산 클러스터**를 만드는 미션.

```
[Docker bridge network: hadoop-net]

  [master 컨테이너]              [worker1 컨테이너]      [worker2 컨테이너]
   ├─ NameNode                    ├─ DataNode             ├─ DataNode
   ├─ SecondaryNameNode           └─ NodeManager           └─ NodeManager
   └─ ResourceManager
        │
        └── ssh로 worker1, worker2에 접속해 DataNode/NodeManager를 "원격으로" 기동
```

핵심 차이: w3m1은 SSH가 "형식상" 필요했던(self-ssh) 반면, w3m2a는 SSH가 **실제로 다른 컨테이너(=다른 서버 취급)에 원격 명령을 내리는 용도**로 쓰인다.

<br>

# W3M1과 겹치는 개념

아래 개념들은 [w3m1.md](./w3m1.md)에 이미 정리되어 있어서 여기서는 생략/요약만 한다.

- HDFS 개념(블록 단위 분산 저장), NameNode/DataNode/SecondaryNameNode 역할
- YARN 개념, ResourceManager/NodeManager 역할
- 네임노드 포맷(`hdfs namenode -format`)의 의미와 "재포맷하면 기존 데이터가 날아간다"는 주의사항
- `hdfs dfs -mkdir/-ls/-put/-get/-cat` 등 HDFS 조작 명령어
- 웹 UI(`:9870` NameNode, `:8088` ResourceManager)의 용도
- `core-site.xml`/`hdfs-site.xml`/`mapred-site.xml`/`yarn-site.xml`이 Hadoop 설정을 담당한다는 것, `hadoop-env.sh`가 셸 환경변수를 담당한다는 것

차이가 나는 값만 정리하면:

| 설정 | w3m1 (단일 노드) | w3m2a (멀티노드) | 이유 |
|---|---|---|---|
| `dfs.replication` | 1 | 2 | DataNode(worker)가 2대라 복제본을 2개까지 만들 수 있음 |
| `fs.defaultFS` | `hdfs://localhost:9000` | `hdfs://master:9000` | NameNode가 다른 컨테이너에서 봐도 접근 가능한 호스트 이름이어야 함 |
| `yarn.resourcemanager.hostname` | `localhost` | `master` | 위와 동일한 이유 |

<br>

# 멀티노드에서 새로 등장하는 개념

## Docker 브리지 네트워크와 컨테이너 간 통신

`docker-compose.yml`에 정의한 `hadoop-net`(driver: bridge) 네트워크에 `master`, `worker1`, `worker2`가 모두 연결된다.
같은 네트워크에 있으면 Docker의 내장 DNS 덕분에 컨테이너를 **IP가 아니라 서비스 이름(hostname)으로** 찾을 수 있다.
그래서 설정 파일에서 `master`, `worker1`, `worker2`라는 이름을 그대로 주소처럼 쓸 수 있는 것.

```yaml
networks:
  hadoop-net:
    aliases: [master]   # 이 컨테이너를 "master"라는 이름으로 네트워크에서 찾을 수 있게 등록
```

<br>

## 노드 한 종류, 이미지는 하나

master/worker1/worker2가 전부 **같은 `Dockerfile`, 같은 이미지(`hadoop-cluster:latest`)** 로 빌드된다.
실행할 때 `HADOOP_NODE_TYPE` 환경변수(`docker-compose.yml`의 `environment:`)만 다르게 주입해서 `entrypoint.sh`가 역할을 나눈다.

```bash
case "$HADOOP_NODE_TYPE" in
  master) ... ;;   # 클러스터 전체를 기동하는 역할
  worker) ... ;;   # sshd만 띄우고 master의 접속을 기다리는 역할
esac
```

이미지를 하나로 통일하는 이유: 노드마다 Dockerfile을 따로 관리할 필요가 없고, **모든 노드가 같은 SSH 키 쌍(`id_rsa`/`authorized_keys`)을 갖게 되어** master가 별도 키 배포 없이 바로 worker에 접속할 수 있다.

<br>

## SSH가 원격 실행으로 쓰이는 이유

w3m1은 `ssh localhost`였지만, 여기서는 master 컨테이너가 `ssh worker1`, `ssh worker2`로 **다른 컨테이너**에 접속해서 그 컨테이너 안의 `hdfs`/`yarn` 데몬을 띄운다.
이게 가능한 이유는 이미지 빌드 시점에 모든 노드에 동일한 키 쌍을 심어두었기 때문 (master의 개인키로 접속 시도 → worker의 `authorized_keys`에 있는 같은 공개키와 매칭되어 인증 통과).

```
Dockerfile 빌드 시:
  ssh-keygen으로 id_rsa/id_rsa.pub 생성
  → id_rsa.pub을 authorized_keys에 복사
  → 이 이미지로 master, worker1, worker2를 각각 빌드/실행
  → 세 컨테이너 모두 "같은 키 쌍"을 가짐 → 서로 비밀번호 없이 ssh 가능
```

<br>

## `workers` 파일

`$HADOOP_CONF_DIR/workers`에 적힌 호스트 목록(`worker1`, `worker2`)을 `start-dfs.sh`/`start-yarn.sh`가 읽어서,
**이 목록에 있는 호스트에 ssh로 접속해 DataNode/NodeManager를 원격 기동**한다. NameNode/ResourceManager/SecondaryNameNode는 스크립트를 실행한 그 노드(master)에서 뜬다.

```
worker1
worker2
```

worker를 늘리려면: `docker-compose.yml`에 서비스 추가 + `config/workers`에 호스트 추가 + `dfs.replication` 값 조정, 이 세 가지가 같이 가야 한다.

<br>

## entrypoint.sh의 master/worker 역할 분기

| 역할 | 하는 일 |
|---|---|
| **master** | 1) 자기 자신 + `workers` 파일의 모든 host에 대해 `nc -z host 22`로 SSH가 뜰 때까지 대기 → 2) 최초 1회만 NameNode 포맷 → 3) `start-dfs.sh`/`start-yarn.sh` 실행 (내부적으로 worker에 ssh 접속) |
| **worker** | sshd만 띄우고 자기 자신의 SSH가 뜰 때까지 대기 후 대기 상태로 남음. 데몬은 master가 ssh로 원격 기동해줌 |

worker 컨테이너 로그에 NameNode/DataNode 관련 메시지가 안 보이는 게 정상. worker의 데몬 로그는 worker 컨테이너 **안의** `$HADOOP_HOME/logs`에 남지만, 그 데몬을 "띄운" 명령 자체는 master 쪽 로그에 찍힌다 (`Starting datanodes` 같은 문구).

<br>

## 클러스터 상태 확인은 노드별로 따로

w3m1은 컨테이너가 하나라 `jps` 한 번으로 5개 데몬을 전부 봤지만, 여기서는 컨테이너가 3개라 **노드별로 따로 확인**해야 한다.

```bash
docker exec master  jps   # NameNode, SecondaryNameNode, ResourceManager
docker exec worker1 jps   # DataNode, NodeManager
docker exec worker2 jps   # DataNode, NodeManager
```

전체 클러스터 관점에서 워커가 몇 대 붙었는지는 master에서 다음으로 확인.
```bash
docker exec master hdfs dfsadmin -report   # Live datanodes (2) 확인
```
YARN 웹 UI(`:8088`)의 Nodes 메뉴에서도 NodeManager가 2대 붙어 있는지 확인 가능.

<br>

## 노드별 데이터 영속성(볼륨)

w3m1은 볼륨이 `name`/`data` 두 개뿐이었지만, 여기서는 **노드마다 별도의 호스트 디렉토리**를 마운트한다.

| 노드 | 마운트 | 저장하는 것 |
|---|---|---|
| master | `./data/master/name:/hadoop/dfs/name` | NameNode 메타데이터 |
| worker1 | `./data/worker1/data:/hadoop/dfs/data` | worker1의 HDFS 블록 |
| worker2 | `./data/worker2/data:/hadoop/dfs/data` | worker2의 HDFS 블록 |

`docker compose down` 후 `up`을 다시 해도 각 노드가 자기 볼륨을 그대로 다시 물기 때문에, 재포맷 없이 데이터가 복원된다.

<br>

## MapReduce가 실제로 "분산" 처리되는 걸 확인하는 법

```bash
docker exec master bash -c 'yarn jar $HADOOP_HOME/share/hadoop/mapreduce/hadoop-mapreduce-examples-*.jar wordcount /input /output'
```
- 잡을 던지면 ResourceManager(master)가 스케줄링하고, 실제 map/reduce task는 NodeManager가 떠 있는 worker1/worker2 쪽 컨테이너에서 실행된다.
- YARN 웹 UI(`:8088`)에서 Job 상세 화면에 들어가면 어떤 노드가 어떤 task를 처리했는지 확인 가능 — 이게 "master 혼자 다 하는 게 아니라 워커들에게 작업이 분산됐다"는 증거.
- 호스트 셸(zsh 등)에서 `$HADOOP_HOME`이나 `*` 와일드카드를 그대로 쓰면 **호스트 쪽 셸이 먼저 이걸 해석**하려다 실패한다(`no matches found`). `docker exec`으로 넘기는 명령 전체를 따옴표로 감싸서 컨테이너 안의 bash가 해석하게 해야 한다.

<br>

## (트러블슈팅) Hadoop 다운로드가 비정상적으로 느릴 때

Dockerfile에서 Hadoop tar.gz를 받는 미러 URL에 따라 속도 차이가 크다.

- `archive.apache.org`: 과거 릴리즈를 보관하는 아카이브 서버라 다운로드가 매우 느림 (수십 분 이상 걸릴 수 있음)
- `dlcdn.apache.org`: 최신 릴리즈를 CDN으로 배포하는 미러라 훨씬 빠름

같은 버전이라도 어느 도메인에서 받는지에 따라 빌드 시간이 크게 달라지므로, 빌드가 유독 오래 걸린다면 제일 먼저 Dockerfile의 다운로드 URL부터 의심.

<br>

## (참고) 같은 이미지 태그를 여러 서비스가 동시에 빌드할 때

`docker-compose.yml`에서 master/worker1/worker2가 전부 `image: hadoop-cluster:latest`로 같은 태그를 쓰면,
`docker compose build`가 세 서비스를 병렬로 빌드하면서 **이미지 태그를 서로 먼저 쓰려고 경합**해 일부 서비스가 `already exists` 에러로 실패 표시될 수 있다.
내용물은 어차피 동일해서 실제 이미지는 정상적으로 만들어지므로, `docker images hadoop-cluster:latest`로 이미지 존재만 확인하면 된다.
