#!/usr/bin/env python3
import sys
import re
import csv
import io

WORD_RE = re.compile(r"[\w'']+")

POSITIVE_WORDS = {
    "good", "great", "awesome", "amazing", "excellent", "fantastic",
    "wonderful", "love", "loved", "loving", "happy", "glad", "excited",
    "best", "beautiful", "nice", "fun", "cool", "perfect", "thanks",
    "thank", "grateful", "yay", "lol", "haha", "smile", "smiling",
    "enjoy", "enjoyed", "enjoying", "sweet", "cute", "proud", "win",
    "winning", "success", "brilliant", "fabulous", "delighted", "blessed"
}

NEGATIVE_WORDS = {
    "bad", "sad", "hate", "hated", "hating", "angry", "mad", "upset",
    "sorry", "sick", "tired", "hurt", "cry", "crying", "annoying",
    "annoyed", "terrible", "horrible", "awful", "worst", "sucks",
    "ugh", "boring", "bored", "stupid", "worried", "worry", "pain",
    "broken", "miss", "missing", "lonely", "depressed", "fail",
    "failed", "disappointed", "disappointing", "hurts", "damn", "ugly"
}

class WordMapper:
    def tokenize(self, text):
        return WORD_RE.findall(text.lower())

    def parse_tweet_text(self, line):
        row = list(csv.reader([line]))
        return row[0][5]

    def classify(self, text):
        words = self.tokenize(text)
        pos_count = sum(1 for word in words if word in POSITIVE_WORDS)  
        neg_count = sum(1 for word in words if word in NEGATIVE_WORDS)  

        if pos_count > neg_count:
            return "positive"
        elif pos_count < neg_count:
            return "negative"
        else:
            return "neutral"

    def run(self):
        sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding="latin1")

        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue

            try:
                text = self.parse_tweet_text(line)
            except (csv.Error, IndexError):
                continue

            category = self.classify(text)
            print(f"{category}\t1")

if __name__ == "__main__":
    WordMapper().run()