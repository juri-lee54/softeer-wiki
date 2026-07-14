#!/bin/bash
# 셔뱅(shebang). 이 파일은 /bin/bash(배시 셸)로 실행해라.

# 실행 중 실패하면 중단하는 옵션
set -euo pipefail

HADOOP_HOME=${HADOOP_HOME:-/opt/hadoop}
HADOOP_CONF_DIR=${HADOOP_CONF_DIR:-/opt/hadoop/etc/hadoop}
# [멀티노드] docker-compose.yml에서 넘겨주는 HADOOP_NODE_TYPE으로 master/worker 역할을 구분
ROLE=${HADOOP_NODE_TYPE:-worker}

NAMENODE_DIR=/hadoop/dfs/name

# ---------- SSH 데몬 실행 ----------
# start-dfs.sh / start-yarn.sh 는 내부적으로 ssh를 통해 각 노드의 데몬을 띄우므로
# master, worker 모두 sshd가 떠 있어야 함
mkdir -p /run/sshd
/usr/sbin/sshd -D &

wait_for_ssh() {
    local host="$1"
    local tries=0

    echo ">>> ${host}:22 가 뜨기를 기다리는 중..."

    until nc -z "$host" 22 2>/dev/null; do
        tries=$((tries + 1))

        if [ "$tries" -ge 60 ]; then
            echo ">>> ${host}:22 대기 시간 초과"
            return 1
        fi

        sleep 2
    done

    echo ">>> ${host}:22 준비 완료."
}

case "$ROLE" in
    master)

        # [멀티노드] 자기 자신과 workers 파일에 적힌 모든 worker의 ssh가 뜰 때까지 대기
        wait_for_ssh localhost

        while read -r host; do
            [[ -z "$host" || "$host" =~ ^# ]] && continue
            wait_for_ssh "$host"
        done < "${HADOOP_CONF_DIR}/workers"

        # ---------- 네임노드 최초 실행 시에만 포맷 ----------
        if [ ! -d "${NAMENODE_DIR}/current" ]; then
            echo ">>> NameNode가 아직 포맷되지 않았습니다. 포맷을 진행합니다..."
            hdfs namenode -format -force -nonInteractive
        else
            echo ">>> 기존 NameNode 데이터가 발견되었습니다. 포맷을 건너뜁니다."
        fi

        # ---------- HDFS/YARN 데몬을 SSH를 통해 실행 ----------
        # start-dfs.sh: master에서 namenode/secondarynamenode를,
        #               workers 파일에 적힌 각 worker에는 ssh로 접속해 datanode를 띄움
        echo ">>> Starting HDFS..."
        start-dfs.sh

        # start-yarn.sh: master에서 resourcemanager를,
        #                workers 파일에 적힌 각 worker에는 ssh로 접속해 nodemanager를 띄움
        echo ">>> Starting YARN..."
        start-yarn.sh

        echo ">>> Hadoop 서비스가 시작되었습니다."
        echo ">>> HDFS Web UI : http://localhost:9870"
        echo ">>> YARN Web UI : http://localhost:8088"
        ;;

    worker)

        # [멀티노드] master가 ssh로 접속해 datanode/nodemanager를 원격 실행하므로
        # worker는 sshd만 띄운 채 대기
        wait_for_ssh localhost
        echo ">>> Worker 노드 대기 중. master가 ssh로 접속해 데몬을 띄웁니다."
        ;;

    *)

        echo "알 수 없는 HADOOP_NODE_TYPE: ${ROLE}"
        exit 1
        ;;
esac

echo ">>> ${ROLE} 노드가 준비되었습니다."

# 도커 컨테이너가 종료되는 걸 막는 용도
tail -f /dev/null
