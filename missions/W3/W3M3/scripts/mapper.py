#!/usr/bin/env python3
import sys
import re

WORD_RE = re.compile(r"[\w'’]+")  

class WordMapper:
    def tokenize(self, line):
        return WORD_RE.findall(line.lower()) # ['hello', 'python', '3', 'world']
        
    def run(self):
        for line in sys.stdin:
            for word in self.tokenize(line):
                print(f"{word}\t1")

if __name__=="__main__":
    WordMapper().run()