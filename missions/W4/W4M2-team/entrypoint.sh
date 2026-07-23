#!/bin/bash
# Spark 데몬 스크립트(start-master.sh 등)는 백그라운드로 실행되는데,
# 백그라운드 실행 시 컨테이너의 메인 프로세스(PID 1)가 바로 끝나버려서 컨테이너 자체가 죽어버림. 
# 그래서 spark-class를 포그라운드로 직접 실행

set -e

# docker-compose에서 넘겨준 SPARK_MODE 환경변수(master 또는 worker)로 분기
if [ "$SPARK_MODE" = "master" ]; then
    # 마스터 노드 실행: 7077(통신 포트), 8080(웹 UI) 오픈
    exec /opt/spark/bin/spark-class org.apache.spark.deploy.master.Master \
        --host 0.0.0.0 \
        --port 7077 \
        --webui-port 8080

elif [ "$SPARK_MODE" = "worker" ]; then
    # 워커 노드 실행: SPARK_MASTER_URL 환경변수로 접속할 마스터 주소를 전달받음
    exec /opt/spark/bin/spark-class org.apache.spark.deploy.worker.Worker \
        "$SPARK_MASTER_URL" \
        --webui-port 8081

else
    echo "SPARK_MODE 환경변수를 master 또는 worker 로 지정해주세요. (현재 값: '$SPARK_MODE')"
    exit 1
fi
