#!/usr/bin/env python3
"""
Parse and separate timestamp and regular comments from combined_data.jsonl
Creates separate JSON files for each comment type
"""

import json
import os

def parse_comments(input_file, output_dir='output_dir'):
    """Parse comments and transcript from combined data and save separately."""
    
    regular_comments_all = []
    timestamp_comments_all = []
    transcript_all = []
    
    # Read the combined data file
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                
                data = json.loads(line)
                
                # Extract comments
                regular_comments_all.extend(data.get('regular_comments', []))
                timestamp_comments_all.extend(data.get('timestamp_comments', []))
                
                # Extract transcript
                transcript_data = data.get('transcript', [])
                if transcript_data:
                    transcript_all.extend(transcript_data)
    
    except FileNotFoundError:
        print(f"Error: File not found: {input_file}")
        return False
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON: {e}")
        return False
    
    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)
    
    # Save regular comments
    regular_output = os.path.join(output_dir, 'regular_comments.json')
    with open(regular_output, 'w', encoding='utf-8') as f:
        json.dump(regular_comments_all, f, ensure_ascii=False, indent=2)
    print(f"✓ Regular comments ({len(regular_comments_all)}개): {regular_output}")
    
    # Save timestamp comments
    timestamp_output = os.path.join(output_dir, 'timestamp_comments.json')
    with open(timestamp_output, 'w', encoding='utf-8') as f:
        json.dump(timestamp_comments_all, f, ensure_ascii=False, indent=2)
    print(f"✓ Timestamp comments ({len(timestamp_comments_all)}개): {timestamp_output}")
    
    # Save transcript
    transcript_output = os.path.join(output_dir, 'transcript.json')
    with open(transcript_output, 'w', encoding='utf-8') as f:
        json.dump(transcript_all, f, ensure_ascii=False, indent=2)
    print(f"✓ Transcript ({len(transcript_all)}개): {transcript_output}")
    
    # Summary
    print(f"\n=== 요약 ===")
    print(f"일반 댓글: {len(regular_comments_all)}개")
    print(f"타임스탬프 댓글: {len(timestamp_comments_all)}개")
    print(f"자막: {len(transcript_all)}개")
    print(f"총합: {len(regular_comments_all) + len(timestamp_comments_all) + len(transcript_all)}개")
    
    return True

if __name__ == "__main__":
    import sys
    
    input_file = sys.argv[1] if len(sys.argv) > 1 else 'output_dir/combined_data.jsonl'
    output_dir = sys.argv[2] if len(sys.argv) > 2 else 'output_dir'
    
    success = parse_comments(input_file, output_dir)
    sys.exit(0 if success else 1)
