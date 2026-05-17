#!/usr/bin/env python3
import json
import re

data = json.loads(open('output_dir/combined_data.jsonl').readline())
comments_raw = data.get('regular_comments', [])

# Check for various timestamp patterns
patterns = [
    (r'\b(\d{1,2}):(\d{2})(?::(\d{2}))?\b', 'Standard format (M:SS or H:MM:SS)'),
    (r'(\d+분)', 'Minutes (분)'),
    (r'(\d+초)', 'Seconds (초)'),
    (r'\[(\d{1,2}):(\d{2})\]', 'Bracketed [M:SS]'),
    (r'\((\d{1,2}):(\d{2})\)', 'Parenthesized (M:SS)'),
]

print('Scanning all comments for potential timestamp patterns...')
print()

for pattern, desc in patterns:
    count = 0
    examples = []
    for comment in comments_raw:
        text = comment.get('text', '')
        if re.search(pattern, text):
            count += 1
            if len(examples) < 2:
                examples.append(text)
    
    if count > 0:
        print(f'{desc}: {count} comments')
        for ex in examples:
            print(f'  Example: {ex}')
        print()

print()
print('Sample of all comments to see what they look like:')
for i, comment in enumerate(comments_raw[:15]):
    print(f'{i+1}. {comment.get("text", "")}')
