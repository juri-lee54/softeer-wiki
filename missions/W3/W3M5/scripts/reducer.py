#!/usr/bin/env python3
import sys

class WordReducer:
    def parse(self, line):
        movie_id, rating = line.strip().split('\t', 1)
        return (movie_id, float(rating))

    def run(self):
        current_movie = None
        sum_rating = 0.0
        count = 0

        for line in sys.stdin:
            movie_id, rating = self.parse(line)

            if movie_id != current_movie:
                if current_movie != None:
                    print(f"{current_movie}\t{round(sum_rating / count, 1)}")
                current_movie = movie_id
                sum_rating = 0.0
                count = 0
                
            sum_rating += rating
            count += 1

        if current_movie != None:
            print(f"{current_movie}\t{round(sum_rating / count, 1)}")

if __name__ == "__main__":
    WordReducer().run()