from multiprocessing import Process


def print_continent(continent = "Asia"):
    print(f"The name of continent is : {continent}")
    
    
    
if __name__ == "__main__":
    procs = []
    continents = ["America", "Europe", "Africa"]
    
    for i in range(4):
        if i < len(continents):
            p = Process(target=print_continent, args=(continents[i],))
        else:
            p = Process(target=print_continent)
        
        p.start()
        procs.append(p)
        
    for p in procs:
        p.join()
        
        
    