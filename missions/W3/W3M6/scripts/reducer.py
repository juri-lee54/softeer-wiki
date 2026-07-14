#!/usr/bin/env python3
import sys

class ReviewReducer:
    def parse(self, line):
        product_id, rating = line.strip().split('\t', 1)
        return (product_id, float(rating))

    def emit(self, product_id, sum_rating, count):
        print(f"{product_id}\t{count}\t{round(sum_rating / count, 1)}")

    def run(self):
        current_product = None
        sum_rating = 0.0
        count = 0

        for line in sys.stdin:
            product_id, rating = self.parse(line)

            if product_id != current_product:
                if current_product is not None:
                    self.emit(current_product, sum_rating, count)
                current_product = product_id
                sum_rating = 0.0
                count = 0

            sum_rating += rating
            count += 1

        if current_product is not None:
            self.emit(current_product, sum_rating, count)

if __name__ == "__main__":
    ReviewReducer().run()
