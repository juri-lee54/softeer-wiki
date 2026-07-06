from multiprocessing import Queue


if __name__ == "__main__":
    items = ["red", "green", "blue", "black"]
    
    q = Queue()
    
    print("pushing items to queue:")
    for idx, item in enumerate(items):
        q.put(item)
        print(f"item no: {idx + 1} {item}")
    
    
    print("popping items from queue:")
    # idx = 0
    # while not q.empty():
    #     item = q.get()
    #     print(f"item no: {idx} {item}")
    #     idx += 1
    # q.empty()는 동작이 되나 동작을 신뢰할 수 없음
    
    for idx in range(len(items)):
        item = q.get()
        print(f"item no: {idx} {item}")
    