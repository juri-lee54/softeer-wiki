# 목차
- [목차](#목차)
- [미션 설명](#미션-설명)
- [사전 지식](#사전-지식)
- [W3M1/W3M2a와 겹치는 개념](#w3m1w3m2a와-겹치는-개념)
- [실제로 바꾼 설정값](#실제로-바꾼-설정값)
- [새로 배운 핵심 개념](#새로-배운-핵심-개념)

<br>
<br>

# 미션 설명

[w3m2a](./w3m2a.md)에서 만든 멀티노드 Hadoop 클러스터(master + worker1 + worker2)를 대상으로,
**설정을 자동으로 백업/수정/재시작하는 스크립트**와 **그 결과를 검증하는 스크립트**를 작성하는 미션.
클러스터 자체를 새로 만드는 게 아니라, "이미 떠 있는 멀티노드 클러스터를 코드로 안전하게 재구성하는 법"이 핵심.

<br>

# 사전 지식

## 설정 파일
### core-site.xml
- fs.defaultFS : 기본 파일 시스템 URI를 지정
- hadoop.tmp.dir : 임시 디렉토리를 지정
- io.file.buffer.size : 파일 읽기/쓰기를 위한 버퍼 크기를 지정

### hdfs-site.xml
- dfs.replication : HDFS의 기본 복제 계수를 정의
- dfs.blocksize : 기본 블록 크기를 지정
- dfs.namenode.name.dir : 네임노드가 네임스페이스 및 트랜잭션 로그를 저장하는 로컬 파일 시스템의 경로를 지정

### mapred-site.xml
- mapreduce.framework.name : MapReduce에 사용할 프레임워크 이름을 지정
- mapreduce.jobhistory.address : 완료된 MapReduce 작업에 대한 정보에 액세스하는 데 사용되는 JobHistoryServer의 주소를 지정
- mapreduce.task.io.sort.mb : 맵 출력 정렬 시 사용할 메모리 양을 지정

### yarn-site.xml
- yarn.resourcemanager.address : ResourceManager IPC의 주소
- yarn.nodemanager.resource.memory-mb : YARN에서 사용할 수 있는 메모리 양을 결정
- yarn.scheduler.minimum-allocation-mb : ResourceManager에서 각 컨테이너 요청에 대한 최소 할당량을 지정

<br>

# W3M1/W3M2a와 겹치는 개념

아래는 이미 정리돼 있어서 생략/요약만 한다. 자세한 내용은 [w3m1.md](./w3m1.md), [w3m2a.md](./w3m2a.md) 참고.

- HDFS/YARN 기본 개념, NameNode/DataNode/ResourceManager/NodeManager 역할
- Docker 브리지 네트워크 + `aliases`로 컨테이너를 hostname으로 찾는 방식
- 같은 이미지 하나로 master/worker 역할을 `HADOOP_NODE_TYPE`으로 분기하는 구조
- master가 ssh로 worker에 원격 접속해 데몬을 띄우는 방식, `workers` 파일의 역할
- 노드별 `jps` 확인, 노드별 볼륨 마운트로 데이터 영속성 확보
- 같은 이미지 태그를 여러 서비스가 동시에 빌드할 때 `already exists` 경고 나는 것

<br>

# 실제로 바꾼 설정값

| 파일 | 키 | 값 |
|---|---|---|
| core-site.xml | fs.defaultFS | `hdfs://namenode:9000` |
| core-site.xml | hadoop.tmp.dir | `/hadoop/tmp` |
| core-site.xml | io.file.buffer.size | `131072` |
| hdfs-site.xml | dfs.replication | `2` |
| hdfs-site.xml | dfs.blocksize | `134217728` |
| hdfs-site.xml | dfs.namenode.name.dir | `/hadoop/dfs/name` |
| mapred-site.xml | mapreduce.framework.name | `yarn` |
| mapred-site.xml | mapreduce.jobhistory.address | `namenode:10020` |
| mapred-site.xml | mapreduce.task.io.sort.mb | `256` |
| yarn-site.xml | yarn.resourcemanager.address | `namenode:8032` |
| yarn-site.xml | yarn.nodemanager.resource.memory-mb | `8192` |
| yarn-site.xml | yarn.scheduler.minimum-allocation-mb | `1024` |

w3m2a는 호스트명으로 `master`를 썼는데, 이번 미션 스펙은 `namenode`를 요구해서 두 이름이 같은 컨테이너를 가리키도록 alias를 하나 더 추가해야 했다 (아래 참고).

<br>

# 새로 배운 핵심 개념

## 1. 런타임에 설정을 고치면 "그 컨테이너만" 바뀐다

w3m2a에서 배운 건 "빌드 시점에 같은 이미지를 쓴다"였는데, 이번엔 **빌드 이후, 컨테이너가 떠 있는 상태에서** 설정 파일을 스크립트로 고치는 상황이었다. master 컨테이너 안의 `$HADOOP_CONF_DIR`만 고쳤더니, worker1/worker2는 완전히 별개의 컨테이너(= 별개의 파일시스템)라서 여전히 이미지 빌드 시점의 예전 값을 그대로 갖고 있었다.

증상: `yarn.nodemanager.resource.memory-mb`를 8192로 바꿨는데, 실제 `yarn node -list -showDetails`로 보면 worker들은 여전히 2048을 보고함 → YARN 총 메모리가 기대한 16384가 아니라 4096으로 조회됨.

해결: 설정을 다 고친 뒤, `$HADOOP_CONF_DIR/workers` 파일에 적힌 호스트 목록을 읽어서 수정된 파일 4개를 각 워커에 `scp`로 복사하는 단계를 추가. (ssh 키가 이미 전 노드에 공유돼 있어서 비밀번호 없이 바로 가능.)

> 교훈: **멀티노드 클러스터에서 "설정을 바꾼다"는 건 한 곳만 고치는 게 아니라 모든 노드에 동일하게 반영하는 것까지 포함한다.** 빌드 시점 동기화(같은 이미지)와 런타임 동기화(설정 파일 재배포)는 별개의 문제.

<br>

## 2. 설정에 쓰는 호스트명은 반드시 네트워크에서 resolve돼야 한다

`fs.defaultFS`를 `hdfs://namenode:9000`으로 바꾸면, `start-dfs.sh`는 이 URI에서 호스트명(`namenode`)을 뽑아서 **그 호스트에 ssh로 접속해** NameNode를 띄운다. 그런데 docker-compose 네트워크엔 `master`, `worker1`, `worker2`라는 이름만 등록돼 있어서 `namenode`는 resolve가 안 돼 SSH 자체가 실패하고, NameNode가 아예 안 뜨는 상태로 조용히 넘어갔다.

해결: master 서비스의 네트워크 alias에 `namenode`를 추가해서, 같은 컨테이너가 두 이름(`master`, `namenode`) 모두로 찾아지게 함.
```yaml
networks:
  hadoop-net:
    aliases: [master, namenode]
```

> 교훈: 설정 파일에 적는 호스트명은 문법적으로만 맞으면 되는 게 아니라, **실제로 그 이름으로 접속 가능한 네트워크 alias가 존재해야** 클러스터가 진짜로 동작한다.

<br>

## 3. `hdfs getconf`가 사실상 만능이다

`hadoop getconf`, `yarn getconf`는 Hadoop 3.3.6엔 존재하지 않는 서브커맨드였다(`ERROR: getconf is not COMMAND`). 반면 `hdfs getconf -confKey <key>`는 core-site/hdfs-site/mapred-site/yarn-site 설정을 전부 조회할 수 있어서, 12개 설정 검증을 전부 `hdfs getconf` 하나로 처리했다.

<br>

## 4. 재시작 직후엔 NameNode가 safe mode

서비스를 재시작한 직후 곧바로 HDFS에 파일을 쓰거나 MapReduce 잡을 돌리면 "Name node is in safe mode" 에러가 난다. DataNode들의 블록 리포트를 다 받을 때까지 NameNode가 쓰기를 막아두기 때문. `hdfs dfsadmin -safemode wait`로 안전모드가 풀릴 때까지 기다린 뒤 검증을 진행하면 해결된다.

<br>

## 5. `xml.etree.ElementTree`로 `<property>` 값 수정할 때 흔한 실수

- `element.set(key, value)`는 **XML 속성(attribute)**을 다는 것이지, `<value>` 자식 태그의 텍스트를 바꾸는 게 아니다. `<name>`/`<value>`는 `<property>`의 자식 엘리먼트이므로, `pro.find('value').text = 새값`처럼 자식을 찾아서 `.text`를 바꿔야 한다.
- 새 `<property>`를 추가할 때도 마찬가지로 `ET.SubElement(root, 'property')`로 만든 다음, 그 안에 `<name>`, `<value>`를 각각 `ET.SubElement`로 또 만들어서 텍스트를 채워야 한다. `.set()`으로는 안 됨.
- `tree.write(path, encoding=..., xml_declaration=True)` — `write()`에 `version` 파라미터는 없다. `<?xml version="1.0"?>` 선언을 유지하려면 `xml_declaration=True`만 주면 되고 버전은 항상 1.0으로 고정.
- `import datetime` 상태에서 `datetime.now()`를 호출하면 `AttributeError`가 난다(모듈에 `now()`가 없음). `datetime.datetime.now()`로 쓰거나 `from datetime import datetime`으로 임포트해야 `datetime.now()`가 동작한다.

<br>

## 6. 미션 문서 자체의 함정 (`mapreduce.job.tracker`)

과제 설명의 "예상 출력" 예시엔 `mapreduce.job.tracker -> namenode:9001`이 있지만, "기능요구사항"엔 `mapreduce.jobhistory.address`를 `namenode:10020`으로 바꾸라고만 되어 있다. 실제로 클러스터에 물어보면:
```
$ hdfs getconf -confKey mapreduce.job.tracker
Configuration mapreduce.job.tracker is missing.
```
`mapreduce.job.tracker`는 MapReduce v1(JobTracker) 시절 프로퍼티라 `mapreduce.framework.name=yarn`인 클러스터엔 애초에 존재하지 않는다. 예시 출력을 맹신하지 않고 실제 요구사항(기능요구사항 섹션)과 실제 클러스터 동작을 기준으로 판단해야 했던 케이스.

<br>

## 7. 스크립트 설계 패턴

두 스크립트(설정 수정 / 검증) 모두 아래 패턴을 따르게 짰다.
- 각 단계(백업, 수정, 워커 동기화, 재시작 / getconf 확인, replication 확인, MR 잡, YARN 메모리 확인)를 함수 하나씩으로 분리
- 각 함수는 상태 메시지를 출력하고 `True`/`False`를 리턴
- `main()`에서 전체 결과를 집계해서 마지막에 성공/실패 메시지 + `sys.exit(0/1)`
- 하둡 명령 실행은 `subprocess.run(..., check=True, capture_output=True)` + `except subprocess.CalledProcessError`로 에러 원인까지 잡음

자세한 코드와 실행 방법은 `DE/missions/W3/W3M2b/README.md` 참고.
