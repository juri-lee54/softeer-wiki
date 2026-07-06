""" 
multiprocessing.Pool
: 여러 개의 프로세스를 미리 생성해두고(Pool), 반복적인 작업을 병렬로 처리할 수 있게 돕는 고수준 모듈
"""

from multiprocessing import Pool
import time


def work_log(work):
    name, runtime = work
    print(f"Process {name} waiting {runtime} seconds")
    time.sleep(runtime)
    print(f"Process {name} Finished.")
    
    
if __name__ == '__main__':
    work = [
        ("A", 5),
        ("B", 2),
        ("C", 1),
        ("D", 3)    
    ]

    # pool = Pool(processes=2) # Worker 2개 만들기
    # pool.map(work_log, work) # map()함수를 사용하여 work_log() 함수를 병렬로 실행
    # pool.close() # Worker 종료 - 새로운 작업을 받지 않음
    # pool.join()  # 모든 Worker가 종료될 때까지 기다림
    
    # with 블록을 벗어나면 close()와 join()이 자동으로 호출
    with Pool(processes=2) as pool: # Worker 2개 만들기
        pool.map(work_log, work) # map()함수를 사용하여 work_log() 함수를 병렬로 실행

