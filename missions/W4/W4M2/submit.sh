#!/bin/bash
# spark-master 컨테이너 안에서 spark-submit을 실행해 jobs/ 아래 지정한 스크립트를 클러스터에 제출하는 스크립트
# 사용법: ./submit.sh <job_name> [job에 넘길 인자...] (인자를 생략하면 각 job.py에 정의된 기본 경로 사용)
#
# 예:
#   ./submit.sh clean_trips
#   ./submit.sh clean_trips /opt/data /opt/output/cleaned_trips
#   ./submit.sh compute_metrics
#   ./submit.sh peak_hours
#   ./submit.sh weather_correlation

set -e

if [ -z "$1" ]; then
    echo "사용법: ./submit.sh <job_name> [job에 넘길 인자...]"
    echo "  jobs/ 아래 있는 job 이름(확장자 제외)을 지정합니다. 예:"
    echo "    ./submit.sh clean_trips"
    echo "    ./submit.sh compute_metrics"
    echo "    ./submit.sh peak_hours"
    echo "    ./submit.sh weather_correlation"
    exit 1
fi

JOB_NAME=$1
shift

# 호스트 기준 jobs/ 아래 실제로 존재하는 job인지 먼저 확인 (컨테이너 안에서 파일 못 찾는 것보다 여기서 바로 알려주는 게 나음)
if [ ! -f "jobs/${JOB_NAME}.py" ]; then
    echo "jobs/${JOB_NAME}.py 파일을 찾을 수 없습니다."
    exit 1
fi

echo "spark-master 컨테이너 안에서 ${JOB_NAME} 작업 제출..."
echo "인자: $*"

docker exec spark-master \
    spark-submit \
    --master spark://spark-master:7077 \
    --deploy-mode client \
    "/opt/jobs/${JOB_NAME}.py" "$@"

echo "작업 제출 완료. 결과는 호스트 기준 ./output 경로에서 확인하세요."
echo "클러스터 상태 및 작업 진행 상황은 http://localhost:8080 에서 확인 가능합니다."
