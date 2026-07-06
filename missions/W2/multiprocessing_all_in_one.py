from multiprocessing import Process, Queue, current_process
from queue import Empty
import time


def process_task(tasks_to_accomplish, tasks_that_are_done):
    while True:
        try: 
            task = tasks_to_accomplish.get_nowait()
        except Empty:
            break
        
        print(task)
        time.sleep(0.5)
        
        tasks_that_are_done.put(f"{task} is done by Process-{current_process().name}")
    


if __name__ == '__main__':
    task_nums = 10
    worker_nums = 4
    tasks_to_accomplish = Queue()
    tasks_that_are_done = Queue()
    
    for i in range(task_nums):
        tasks_to_accomplish.put(f"Task no {i}")

    procs = []
    
    for i in range(worker_nums):
        p = Process(target=process_task, args=(tasks_to_accomplish, tasks_that_are_done))
        p.start()
        procs.append(p)
        
    for p in procs:
        p.join()
    
    print()
    for _ in range(task_nums):
        print(tasks_that_are_done.get())
    
       