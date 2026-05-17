#!/usr/bin/env python3
import json
import re

data = json.loads(open('output_dir/combined_data.jsonl').readline())

# Check regular comments for timestamp patterns
regular_comments = data.get('regular_comments', [])
print(f"Total regular comments: {len(regular_comments)}\n")

# Check first 10 comments for timestamp patterns
timestamp_pattern = r'\b(\d{1,2}):(\d{2})(?::(\d{2}))?\b'
pattern_count = 0

for i, comment in enumerate(regular_comments[:10]):
    text = comment.get('text', '')
    matches = re.findall(timestamp_pattern, text)
    if matches:
        pattern_count += 1
        print(f"[{i}] {text}")
        print(f"    Matches: {matches}\n")
    else:
        print(f"[{i}] {text[:80]}...")
        print(f"    No matches\n")

print(f"\nTotal comments with timestamp pattern in first 10: {pattern_count}")

# Count all comments that contain timestamp pattern
all_with_pattern = 0
for comment in regular_comments:
    text = comment.get('text', '')
    matches = re.findall(timestamp_pattern, text)
    if matches:
        all_with_pattern += 1

print(f"Total comments with timestamp pattern in all {len(regular_comments)}: {all_with_pattern}")
