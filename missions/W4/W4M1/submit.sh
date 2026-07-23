#!/bin/bash
# spark-master 컨테이너 안에서 spark-submit을 실행해 pi.py 작업을 클러스터에 제출하는 스크립트
# 사용법: ./submit.sh [input_path] [output_path]

set -e

# 컨테이너 내부 기준 입력 경로 (기본값). docker-compose에서 ./data:/opt/data 로 마운트되어 있어
# 파티션 수 / 파티션당 샘플 수 설정을 이 CSV 파일에서 읽어옴
INPUT_PATH=${1:-/opt/data/pi_config.csv}
# 컨테이너 내부 기준 출력 경로 (기본값). docker-compose에서 ./output:/opt/output 로 마운트되어 있어
# 호스트의 ./output 폴더에서 결과를 바로 확인 가능
OUTPUT_PATH=${2:-/opt/output/pi_result}

echo "spark-master 컨테이너 안에서 spark-submit 실행..."
echo "input_path=${INPUT_PATH}, output_path=${OUTPUT_PATH}"

docker exec spark-master \
    spark-submit \
    --master spark://spark-master:7077 \
    --deploy-mode client \
    /opt/jobs/pi.py "${INPUT_PATH}" "${OUTPUT_PATH}"

echo "작업 제출 완료. 결과는 호스트 기준 ./output/$(basename "${OUTPUT_PATH}") 경로에서 확인하세요."
echo "클러스터 상태 및 작업 진행 상황은 http://localhost:8080 에서 확인 가능합니다."
