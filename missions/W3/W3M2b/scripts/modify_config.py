import shutil
from datetime import datetime
import xml.etree.ElementTree as ET
import os
import subprocess
import sys


def backup_file(path):
    print(f'Backing up {os.path.basename(path)}...')
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        shutil.copy2(path, f'{path}.bak.{timestamp}')
        return True
    except OSError as e:
        print(f'fail backup : {e}')
        return False
    

def set_property(xml_path, confs):
    print(f'Modifying {os.path.basename(xml_path)}...')

    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
            
        for conf in confs:
            modify = False
            for pro in root.findall('property'):
                pro_name = pro.find('name').text
            
                if pro_name == conf[0]:
                    value_elem = pro.find('value')
                    value_elem.text = conf[1]
                    modify = True
        
            if modify == False:
                prop_elem = ET.SubElement(root, 'property')
                name_elem = ET.SubElement(prop_elem, 'name')
                name_elem.text = conf[0]
                value_elem = ET.SubElement(prop_elem, 'value')
                value_elem.text = conf[1]
        
        tree.write(xml_path, encoding="UTF-8", xml_declaration=True)
        return True
    except OSError as e:
        print(f'fail modify : {e}')
        return False
    
def get_workers(conf_path):
    workers_file = os.path.join(conf_path, "workers")
    with open(workers_file) as f:
        return [line.strip() for line in f if line.strip() and not line.startswith("#")]


def sync_to_workers(conf_path, fnames):
    try:
        workers = get_workers(conf_path)
    except OSError as e:
        print(f'fail read workers file: {e}')
        return False

    paths = [os.path.join(conf_path, fname) for fname in fnames]
    all_ok = True
    for worker in workers:
        print(f'Syncing config to {worker}...')
        try:
            subprocess.run(["scp"] + paths + [f"{worker}:{conf_path}/"],
                            check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as e:
            print(f'fail sync to {worker}: {e.stderr}')
            all_ok = False
    return all_ok


def restart_hadoop():
    shlist = [('Stopping Hadoop DFS...', "stop-dfs.sh"),
              ('Stopping YARN...', "stop-yarn.sh"),
              ('Starting Hadoop DFS...', "start-dfs.sh"),
              ('Starting YARN...', "start-yarn.sh")]
        
    try:
        for item in shlist:
            print(item[0])
            subprocess.run([item[1]], check=True, text=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"fail restart: {e.returncode}")
        return False
    

def main():
    try:
        conf_path = sys.argv[1]
    except IndexError:
        print("경고: 입력 파일이 지정되지 않음")
        sys.exit(1)   


    if os.path.isdir(conf_path):
        print("존재하는 path")
    else:
        print("존재하지 않는 path")
        sys.exit(1)
    
    modlist = [("core-site.xml", [("fs.defaultFS", "hdfs://namenode:9000"),
                                  ("hadoop.tmp.dir", "/hadoop/tmp"),
                                  ("io.file.buffer.size", "131072")]),
               ("hdfs-site.xml", [("dfs.replication", "2"),
                                  ("dfs.blocksize", "134217728"),
                                  ("dfs.namenode.name.dir", "/hadoop/dfs/name")]),
               ("mapred-site.xml", [("mapreduce.framework.name", "yarn"),
                                   ("mapreduce.jobhistory.address", "namenode:10020"),
                                   ("mapreduce.task.io.sort.mb", "256")]),
               ("yarn-site.xml", [("yarn.resourcemanager.address", "namenode:8032"),
                                  ("yarn.nodemanager.resource.memory-mb", "8192"),
                                  ("yarn.scheduler.minimum-allocation-mb", "1024")])]
    
    all_ok = True
    for fname, values in modlist:
        fpath = os.path.join(conf_path, fname)
        if not backup_file(fpath):
            all_ok = False
            continue
        if not set_property(fpath, values):
            all_ok = False

    fnames = [fname for fname, _ in modlist]
    if not sync_to_workers(conf_path, fnames):
        all_ok = False

    if not restart_hadoop():
        all_ok = False

    if all_ok:
        print("Configuration changes applied and services restarted.")
        sys.exit(0)
    else:
        print("일부 단계에서 실패가 있었습니다. 위 로그를 확인하세요.")
        sys.exit(1)

if __name__ == "__main__":
    main()