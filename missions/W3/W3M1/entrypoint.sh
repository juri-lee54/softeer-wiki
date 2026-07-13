#! /bin/bash
# 셔뱅(shebang). 이 파일은 /bin/bash(배시 셸)로 실행해라.

# 실행 중 실패하면 중단하는 옵션
set -e

# ---------- 네임노드 최초 실행 시에만 포맷 ----------
# -d: "이게 디렉토리로 존재하는가, ! : 아니다
if [ ! -d "/hadoop/dfs/name/current" ]; then
    echo ">>> NameNode가 아직 포맷되지 않았습니다. 포맷을 진행합니다..."
    $HADOOP_HOME/bin/hdfs namenode -format -force -nonInteractive
    # -format: HDFS 메타데이터를 새로 초기화
    # -force : Y/N 질문 없이 강제 실행
    # -nonInteractive : 대화형X
else
    echo ">>> 기존 NameNode 데이터가 발견되었습니다. 포맷을 건너뜁니다."
fi

# ---------- HDFS 데몬을 SSH/pdsh 없이 로컬에서 직접 실행 ----------
$HADOOP_HOME/bin/hdfs --daemon start namenode
$HADOOP_HOME/bin/hdfs --daemon start datanode
$HADOOP_HOME/bin/hdfs --daemon start secondarynamenode

# ---------- YARN 데몬을 SSH/pdsh 없이 로컬에서 직접 실행 ----------
$HADOOP_HOME/bin/yarn --daemon start resourcemanager
$HADOOP_HOME/bin/yarn --daemon start nodemanager


echo ">>> Hadoop 서비스가 시작되었습니다."
echo ">>> HDFS Web UI : http://localhost:9870"
echo ">>> YARN Web UI : http://localhost:8088"

# 도커 컨테이너가 종료되는 걸 막는 동시에, docker logs로 hadoop 로그를 보기 위함
tail -f $HADOOP_HOME/logs/*.log
# tail -f: 파일의 끝부분을 계속 지켜보면서, 새로운 내용이 추가될 때마다 화면에 출력하는 명령. 파일이 끝나도 종료되지 않고 대기
# $HADOOP_HOME/logs/*.log : Hadoop의 각 데몬(NameNode, DataNode 등)이 쓰는 로그 파일 전부를 대상으로 함
