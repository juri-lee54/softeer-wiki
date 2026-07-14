# Minimal overrides layered on top of Hadoop's built-in hadoop-env.sh defaults.
export JAVA_HOME=${JAVA_HOME:-/opt/java/openjdk}
export HADOOP_HOME=${HADOOP_HOME:-/opt/hadoop}
export HADOOP_CONF_DIR=${HADOOP_CONF_DIR:-/opt/hadoop/etc/hadoop}
export HADOOP_LOG_DIR=${HADOOP_HOME}/logs