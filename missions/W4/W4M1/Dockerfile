# Java 17(JDK)이 설치된 이미지를 베이스로 사용 (Spark는 JVM 위에서 동작)
# openjdk 공식 이미지는 Docker Hub에서 더 이상 유지보수되지 않아 (deprecated) eclipse-temurin으로 대체
# Spark 4.x부터 Java 11 지원이 종료되어 Java 17 이상이 필요함
FROM eclipse-temurin:17-jdk-jammy

# apt-get 설치 중 지역/시간대 등을 묻는 대화형 프롬프트가 뜨지 않도록 설정
ENV DEBIAN_FRONTEND=noninteractive

# 빌드 시점에 값을 주입할 수 있는 변수 선언 (docker build --build-arg 로 덮어쓰기 가능)
# 다운로드할 Spark/Hadoop 버전을 지정
ARG SPARK_VERSION=4.2.0
ARG HADOOP_VERSION=3

# Python(스크립트 실행용), wget/curl/tar(Spark 압축파일 다운로드 및 해제용) 설치
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    wget \
    curl \
    tar \
    && rm -rf /var/lib/apt/lists/*

# eclipse-temurin 이미지는 JAVA_HOME(/opt/java/openjdk)을 기본 제공하므로
# openjdk:11-slim 때 필요했던 심볼릭 링크 생성 작업은 더 이상 필요 없음
ENV JAVA_HOME=/opt/java/openjdk

# Spark 설치 위치
ENV SPARK_HOME=/opt/spark
# spark-submit, spark-class 등 Spark 커맨드를 어디서든 실행할 수 있도록 PATH에 추가
ENV PATH=$SPARK_HOME/bin:$SPARK_HOME/sbin:$PATH

# 지정한 버전의 Spark 배포판을 다운로드 -> 압축 해제 -> SPARK_HOME 위치로 이동 -> 압축파일 삭제
# archive.apache.org는 과거 버전 보관용 서버라 느림 -> CDN이 붙은 dlcdn(공식 배포 서버) 사용
RUN wget https://dlcdn.apache.org/spark/spark-${SPARK_VERSION}/spark-${SPARK_VERSION}-bin-hadoop${HADOOP_VERSION}.tgz -O /tmp/spark.tar.gz \
    && tar -xzf /tmp/spark.tar.gz -C /opt/ \
    && mv /opt/spark-${SPARK_VERSION}-bin-hadoop${HADOOP_VERSION} ${SPARK_HOME} \
    && rm /tmp/spark.tar.gz

# 컨테이너가 시작될 때 마스터/워커 중 무엇으로 뜰지 분기하는 스크립트 복사
COPY entrypoint.sh /opt/entrypoint.sh
RUN chmod +x /opt/entrypoint.sh

# Spark 마스터 통신 포트(7077), 마스터 웹 UI(8080), 워커 웹 UI(8081) 노출
# 실제 호스트 포트 매핑은 docker-compose.yml에서 지정
EXPOSE 7077 8080 8081

# 컨테이너 시작 시 entrypoint.sh를 실행 -> 이 안에서 SPARK_MODE 값에 따라 master/worker 결정
ENTRYPOINT ["/opt/entrypoint.sh"]
