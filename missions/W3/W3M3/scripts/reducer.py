#!/usr/bin/env python3
import sys

class WordReducer:
    def parse(self, line):
        word, count = line.strip().split('\t', 1)
        return (word, int(count))

    def run(self):
        current_word = None
        current_count = 0

        for line in sys.stdin:
            word, count = self.parse(line)

            if word == current_word:
                current_count += count
            else:
                if current_word is not None:
                    print(f"{current_word}\t{current_count}")
                    
                current_word = word
                current_count = count

        if current_word is not None:
            print(f"{current_word}\t{current_count}")

if __name__ == "__main__":
    WordReducer().run()