#!/usr/bin/env python3
import sys

class ReviewMapper:
    def run(self):
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue

            fields = line.split(",")

            try:
                product_id = fields[1]
                rating = float(fields[2])
            except (IndexError, ValueError):
                continue

            print(f"{product_id}\t{rating}")

if __name__ == "__main__":
    ReviewMapper().run()
