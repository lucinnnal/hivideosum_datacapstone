#!/usr/bin/env python3
"""
Batch YouTube Data Collector
Reads YouTube URLs from a JSONL file and collects combined data for each video.
"""

import json
import sys
import os
from datetime import datetime
import youtube_collector

def load_urls_from_jsonl(jsonl_file):
    """Load YouTube URLs from JSONL file."""
    urls = []
    try:
        with open(jsonl_file, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    url = data.get('url') or data.get('video_url') or data.get('link') or data.get('youtube_url')
                    if url:
                        urls.append({
                            'url': url,
                            'line': line_num,
                            'data': data
                        })
                    else:
                        print(f"Warning: No URL found in line {line_num}")
                except json.JSONDecodeError as e:
                    print(f"Warning: Invalid JSON at line {line_num}: {e}")
        return urls
    except FileNotFoundError:
        print(f"Error: File not found: {jsonl_file}")
        return []
    except Exception as e:
        print(f"Error reading file: {e}")
        return []

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Batch YouTube Data Collector")
    parser.add_argument("jsonl_file", help="Input JSONL file with URLs")
    parser.add_argument("output_dir", nargs='?', default="output", help="Output directory")
    parser.add_argument("--max-comments", "-m", type=int, default=1000, 
                        help="Maximum number of comments to collect per video (default: 1000)")
    parser.add_argument("--sort-by", "-s", type=int, choices=[0, 1], default=0,
                        help="Sort comments by: 0 for Popular, 1 for Recent (default: 0)")
    
    args = parser.parse_args()
    
    jsonl_file = args.jsonl_file
    output_dir = args.output_dir
    max_comments = args.max_comments
    sort_by = args.sort_by
    
    print(f"Batch YouTube Data Collector")
    print(f"=" * 60)
    print(f"Input file: {jsonl_file}")
    print(f"Output directory: {output_dir}")
    print(f"Max comments: {max_comments}")
    print(f"Sort by: {'Popular' if sort_by == 0 else 'Recent'}")
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"=" * 60)
    print()
    
    os.makedirs(output_dir, exist_ok=True)
    combined_output_file = os.path.join(output_dir, "combined_data.jsonl")
    
    url_entries = load_urls_from_jsonl(jsonl_file)
    
    if not url_entries:
        print("No URLs found in the input file.")
        sys.exit(1)
    
    print(f"Found {len(url_entries)} URL(s) to process\n")
    
    results = []
    success_count = 0
    failed_count = 0
    
    with open(combined_output_file, 'w', encoding='utf-8') as f_out:
        for idx, entry in enumerate(url_entries, 1):
            url = entry['url']
            line_num = entry['line']
            
            print(f"[{idx}/{len(url_entries)}] Processing line {line_num}: {url}")
            print("-" * 60)
            
            try:
                data = youtube_collector.collect_video_data(
                    video_url=url, 
                    max_regular=max_comments, 
                    max_timestamp=200, 
                    sort_by=sort_by
                )
                
                # Write to combined JSONL immediately
                f_out.write(json.dumps(data, ensure_ascii=False) + '\n')
                f_out.flush()
                
                if data['success']:
                    print("✓ Success\n")
                    success_count += 1
                else:
                    print("✗ Failed to collect complete data\n")
                    failed_count += 1
                
                results.append({
                    'url': url,
                    'line': line_num,
                    'success': data['success']
                })
                
            except Exception as e:
                print(f"✗ Failed with error: {e}\n")
                failed_count += 1
                results.append({
                    'url': url,
                    'line': line_num,
                    'success': False,
                    'error': str(e)
                })
    
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total processed: {len(results)}")
    print(f"  ✓ Successful: {success_count}")
    print(f"  ✗ Failed: {failed_count}")
    print(f"\nCombined data saved to: {combined_output_file}")
    
    log_file = os.path.join(output_dir, 'batch_results.json')
    with open(log_file, 'w', encoding='utf-8') as f:
        json.dump({
            'timestamp': datetime.now().isoformat(),
            'input_file': jsonl_file,
            'total': len(results),
            'successful': success_count,
            'failed': failed_count,
            'results': results
        }, f, ensure_ascii=False, indent=2)
    print(f"Results log saved to: {log_file}")

if __name__ == "__main__":
    main()
