import subprocess
import sys
import json
from urllib import request

# 주의: 이 Hadoop 버전은 'hadoop getconf', 'yarn getconf' 서브커맨드가 없다.
# ('ERROR: getconf is not COMMAND nor fully qualified CLASSNAME.')
# 'hdfs getconf -confKey'가 core/hdfs/mapred/yarn 설정을 전부 읽어오므로 항상 hdfs로 실행한다.
EXPECTED_CONFIGS = [
    ("fs.defaultFS", "hdfs://namenode:9000"),
    ("hadoop.tmp.dir", "/hadoop/tmp"),
    ("io.file.buffer.size", "131072"),
    ("dfs.replication", "2"),
    ("dfs.blocksize", "134217728"),
    ("dfs.namenode.name.dir", "/hadoop/dfs/name"),
    ("mapreduce.framework.name", "yarn"),
    ("mapreduce.jobhistory.address", "namenode:10020"),
    ("mapreduce.task.io.sort.mb", "256"),
    ("yarn.resourcemanager.address", "namenode:8032"),
    ("yarn.nodemanager.resource.memory-mb", "8192"),
    ("yarn.scheduler.minimum-allocation-mb", "1024"),
]

RM_WEBAPP = "http://master:8088"
HDFS_TEST_DIR = "/user/root/verify_test"
HDFS_TEST_FILE = f"{HDFS_TEST_DIR}/verify_test.txt"
LOCAL_TEST_FILE = "/tmp/verify_test.txt"
EXPECTED_REPLICATION = 2
EXPECTED_NM_MEMORY_MB = 8192
EXPECTED_NODE_COUNT = 2


def run_getconf(key):
    cmd = ["hdfs", "getconf", "-confKey", key]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return cmd, result.stdout.strip()


def check(key, expected):
    cmd, actual = run_getconf(key)
    if actual == expected:
        print(f"PASS: {cmd} -> {actual}")
        return True
    else:
        print(f"FAIL: {cmd} -> {actual} (expected {expected})")
        return False


def wait_for_safemode():
    print("Waiting for NameNode to leave safe mode...")
    subprocess.run(["hdfs", "dfsadmin", "-safemode", "wait"],
                   capture_output=True, text=True, timeout=120)


def check_replication():
    try:
        with open(LOCAL_TEST_FILE, "w") as f:
            f.write("hadoop cluster verification test file\n")

        subprocess.run(["hdfs", "dfs", "-mkdir", "-p", HDFS_TEST_DIR],
                        check=True, capture_output=True, text=True)
        subprocess.run(["hdfs", "dfs", "-put", "-f", LOCAL_TEST_FILE, HDFS_TEST_FILE],
                        check=True, capture_output=True, text=True)

        result = subprocess.run(["hdfs", "dfs", "-stat", "%r", HDFS_TEST_FILE],
                                 check=True, capture_output=True, text=True)
        actual_rep = result.stdout.strip()

        if actual_rep == str(EXPECTED_REPLICATION):
            print(f"PASS: Replication factor is {actual_rep}")
            return True
        else:
            print(f"FAIL: Replication factor is {actual_rep} (expected {EXPECTED_REPLICATION})")
            return False
    except subprocess.CalledProcessError as e:
        print(f"FAIL: Replication check error - {e.stderr}")
        return False


def check_mapreduce_job():
    output_dir = f"{HDFS_TEST_DIR}/output"
    subprocess.run(["hdfs", "dfs", "-rm", "-r", "-f", output_dir],
                    capture_output=True, text=True)

    # $HADOOP_HOME과 * 와일드카드를 컨테이너 내부 bash가 해석하도록 bash -c로 감싼다
    job_cmd = (
        "yarn jar $HADOOP_HOME/share/hadoop/mapreduce/hadoop-mapreduce-examples-*.jar "
        f"wordcount {HDFS_TEST_FILE} {output_dir}"
    )
    result = subprocess.run(["bash", "-c", job_cmd], capture_output=True, text=True)

    if result.returncode == 0:
        print("PASS: MapReduce wordcount job completed successfully using YARN")
        return True
    else:
        print(f"FAIL: MapReduce job failed (returncode={result.returncode})")
        print(result.stderr[-1000:])
        return False


def check_yarn_total_memory():
    try:
        with request.urlopen(f"{RM_WEBAPP}/ws/v1/cluster/metrics", timeout=10) as resp:
            data = json.load(resp)

        metrics = data["clusterMetrics"]
        total_mb = metrics["totalMB"]
        total_nodes = metrics["totalNodes"]
        expected_total = EXPECTED_NM_MEMORY_MB * EXPECTED_NODE_COUNT

        if total_mb == expected_total and total_nodes == EXPECTED_NODE_COUNT:
            print(f"PASS: YARN total memory is {total_mb}MB across {total_nodes} nodes")
            return True
        else:
            print(
                f"FAIL: YARN total memory is {total_mb}MB across {total_nodes} nodes "
                f"(expected {expected_total}MB across {EXPECTED_NODE_COUNT} nodes)"
            )
            return False
    except Exception as e:
        print(f"FAIL: Could not query ResourceManager - {e}")
        return False


def main():
    results = []

    for key, expected in EXPECTED_CONFIGS:
        results.append(check(key, expected))

    wait_for_safemode()
    results.append(check_replication())
    results.append(check_mapreduce_job())
    results.append(check_yarn_total_memory())

    total = len(results)
    passed = sum(results)
    print(f"\n{passed}/{total} checks passed")

    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
