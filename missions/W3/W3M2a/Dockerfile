## 기본 이미지 (W3M1과 동일)
FROM ubuntu:22.04

## 대화형 질문 옵션 끄기 - apt-get install 시 질문 끄기 위함
ENV DEBIAN_FRONTEND=noninteractive

## 패키지 설치
RUN apt-get update && apt-get install -y \
    openjdk-11-jdk \
    rsync \
    wget \
    curl \
    net-tools \
    netcat-openbsd \
    openssh-server \
    openssh-client \
    sudo \
    && rm -rf /var/lib/apt/lists/*
# rm -rf /var/lib/apt/lists/* : 패키지 설치 후 남는 캐시 목록을 지워서 이미지 용량을 줄임

## 실제 설치된 JDK 경로를 찾아서 고정 경로로 심볼릭 링크 생성
RUN ln -s /usr/lib/jvm/java-11-openjdk-* /usr/lib/jvm/java-11-openjdk-generic

## [멀티노드 추가] master가 ssh로 worker(들)에 접속해 데몬을 띄울 수 있도록
## sshd를 설정하고, 비밀번호 없이 root로 접속 가능한 키를 미리 만들어둠.
## 모든 노드(master/worker)가 같은 이미지로 빌드되어 동일한 키 쌍을 공유하므로
## master -> worker1/worker2 로의 무인증 ssh 접속이 가능해짐
RUN mkdir -p /run/sshd && \
    ssh-keygen -A && \
    sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config && \
    sed -i 's/^#\?PubkeyAuthentication.*/PubkeyAuthentication yes/' /etc/ssh/sshd_config && \
    echo "PasswordAuthentication no" >> /etc/ssh/sshd_config && \
    mkdir -p /root/.ssh && \
    ssh-keygen -t rsa -b 2048 -f /root/.ssh/id_rsa -q -N "" && \
    cp /root/.ssh/id_rsa.pub /root/.ssh/authorized_keys && \
    printf 'Host *\n  StrictHostKeyChecking no\n  UserKnownHostsFile /dev/null\n' > /root/.ssh/config && \
    chmod 700 /root/.ssh && \
    chmod 600 /root/.ssh/id_rsa /root/.ssh/authorized_keys /root/.ssh/config

## 컨테이너 안에서 계속 사용할 환경변수
# 자바 설치 위치
ENV JAVA_HOME=/usr/lib/jvm/java-11-openjdk-generic
ENV HADOOP_VERSION=3.3.6
# Hadoop 설치 위치와 설정 파일 위치
ENV HADOOP_HOME=/opt/hadoop
ENV HADOOP_CONF_DIR=$HADOOP_HOME/etc/hadoop
# [멀티노드 추가] start-dfs.sh/start-yarn.sh 및 MapReduce AppMaster가
# 원격(worker) 노드에서도 같은 경로를 참조할 수 있도록 명시
ENV HADOOP_MAPRED_HOME=$HADOOP_HOME
ENV HADOOP_COMMON_HOME=$HADOOP_HOME
ENV HADOOP_HDFS_HOME=$HADOOP_HOME
ENV HADOOP_YARN_HOME=$HADOOP_HOME

# 어떤 리눅스 사용자로 각 데몬을 실행할지
ENV HDFS_NAMENODE_USER=root
ENV HDFS_DATANODE_USER=root
ENV HDFS_SECONDARYNAMENODE_USER=root
ENV YARN_RESOURCEMANAGER_USER=root
ENV YARN_NODEMANAGER_USER=root
#컨테이너 안 어디서든 hdfs, start-dfs.sh 같은 명령을 경로 지정 없이 사용하기 위함
ENV PATH=$PATH:$JAVA_HOME/bin:$HADOOP_HOME/bin:$HADOOP_HOME/sbin
# [멀티노드 추가] start-dfs.sh/start-yarn.sh가 ssh로 다른 노드(worker)에 접속할 때
# 호스트 키 확인 프롬프트 없이 붙도록 지정
ENV HADOOP_SSH_OPTS="-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"

## Apache 공식 미러에서 Hadoop 압축 파일을 다운로드
RUN wget -q https://dlcdn.apache.org/hadoop/common/hadoop-${HADOOP_VERSION}/hadoop-${HADOOP_VERSION}.tar.gz -O /tmp/hadoop.tar.gz \
    && tar -xzf /tmp/hadoop.tar.gz -C /opt/ \
    && mv /opt/hadoop-${HADOOP_VERSION} ${HADOOP_HOME} \
    && rm /tmp/hadoop.tar.gz
# tar -xzf: /opt/에 압축 풀기
# mv : 풀린 폴더 이름을 ${HADOOP_HOME}으로 바꾸기
# rm : 다 쓴 압축 파일 삭제하기

## 로컬에서 작성한 설정 파일들을 이미지 안 Hadoop 설정 디렉토리로 복사해서 기본값을 덮어씀
COPY config/core-site.xml   $HADOOP_CONF_DIR/core-site.xml
COPY config/hdfs-site.xml   $HADOOP_CONF_DIR/hdfs-site.xml
COPY config/mapred-site.xml $HADOOP_CONF_DIR/mapred-site.xml
COPY config/yarn-site.xml   $HADOOP_CONF_DIR/yarn-site.xml
# [멀티노드 추가] start-dfs.sh/start-yarn.sh가 데몬을 띄울 worker 목록
COPY config/workers         $HADOOP_CONF_DIR/workers

## Hadoop 자체 실행 스크립트(hadoop-env.sh)에 환경 변수 추가
# 위에서 작성한 ENV는 Docker 컨테이너 레벨의 변수일 뿐이고,
# ssh로 접속한 세션에서도 hdfs/yarn 스크립트가 이 값을 읽도록 hadoop-env.sh에 직접 남겨둠
RUN echo "export JAVA_HOME=${JAVA_HOME}" >> $HADOOP_CONF_DIR/hadoop-env.sh \
    && echo "export HDFS_NAMENODE_USER=${HDFS_NAMENODE_USER}" >> $HADOOP_CONF_DIR/hadoop-env.sh \
    && echo "export HDFS_DATANODE_USER=${HDFS_DATANODE_USER}" >> $HADOOP_CONF_DIR/hadoop-env.sh \
    && echo "export HDFS_SECONDARYNAMENODE_USER=${HDFS_SECONDARYNAMENODE_USER}" >> $HADOOP_CONF_DIR/hadoop-env.sh \
    && echo "export YARN_RESOURCEMANAGER_USER=${YARN_RESOURCEMANAGER_USER}" >> $HADOOP_CONF_DIR/hadoop-env.sh \
    && echo "export YARN_NODEMANAGER_USER=${YARN_NODEMANAGER_USER}" >> $HADOOP_CONF_DIR/hadoop-env.sh

## HDFS 메타데이터, 실제 블록 데이터 디렉토리 만들어두기
RUN mkdir -p /hadoop/dfs/name /hadoop/dfs/data
# hdfs-site.xml 가리킬 경로, 볼륨을 연결할 경로

## 컨테이너 시작 시 실행할 스크립트 복사
COPY entrypoint.sh /entrypoint.sh
## 복사한 스크립트에 실행 권한 부여
RUN chmod +x /entrypoint.sh

## 컨테이너 포트 메모
# EXPOSE만으로는 호스트에서 실제로 접속되지 않음 - docker run -p / docker-compose ports 옵션이 함
EXPOSE 9870 9000 8088 9864 9866 8042 19888 22
# 각 HDFS 웹 UI(9870), NameNode RPC(9000), YARN 웹 UI(8088), DataNode 관련 포트(9864, 9866),
# NodeManager(8042), 히스토리 서버(19888)
# 22: sshd, master가 start-dfs.sh/start-yarn.sh로 worker에 접속할 때 내부적으로 사용 (호스트에는 publish 안 함)

## "데이터가 영속되어야 할 곳"이라고 표시
VOLUME ["/hadoop/dfs/name", "/hadoop/dfs/data"]

## 컨테이너가 실행할 때 무조건 이 스크립트를 실행하라고 지정
ENTRYPOINT ["/entrypoint.sh"]
