#!/usr/bin/env python3
import sys

class RatingMapper:
    def run(self):
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue

            fields = line.split(",")

            try:
                movie_id = fields[1]
                rating = float(fields[2])
            except (IndexError, ValueError):
                continue

            print(f"{movie_id}\t{rating}")

if __name__ == "__main__":
    RatingMapper().run()