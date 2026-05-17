#!/usr/bin/env python3
"""
YouTube Transcript and Comment Collector
Collects transcript and comments (separated by timestamp comments) from a YouTube video.
"""

import json
import re
import sys
import argparse

def parse_timestamp(text):
    """
    Parse timestamp patterns from comment text.
    Supports formats like: 
    - 1:23, 12:34, 1:23:45 (MM:SS or H:MM:SS)
    - 1분 23초, 2분 (Korean format)
    - [1:23], (1:23) (bracketed/parenthesized)
    """
    # Standard format: H:MM:SS or M:SS
    standard_pattern = r'(\d{1,2}):(\d{2})(?::(\d{2}))?'
    # Korean format: 분(minutes), 초(seconds)
    korean_pattern = r'(\d+)분\s*(?:(\d+)초)?|(\d+)초'
    # Bracketed or parenthesized
    bracketed_pattern = r'[\[\(](\d{1,2}):(\d{2})(?::(\d{2}))?\][\]\)]'
    
    matches = []
    
    # Try standard format with word boundaries
    m = re.findall(r'\b' + standard_pattern + r'\b', text)
    if m:
        matches.extend(m)
    
    # Try bracketed format (no word boundary needed)
    m = re.findall(bracketed_pattern, text)
    if m:
        matches.extend(m)
    
    # Try Korean format
    m = re.findall(korean_pattern, text)
    if m:
        matches.extend(m)
    
    return matches if matches else None

def get_video_length(video_url):
    """Get video length using yt-dlp."""
    try:
        import yt_dlp
        ydl_opts = {'quiet': True, 'skip_download': True, 'nocheckcertificate': True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            return info.get('duration', 0)
    except Exception as e:
        print(f"Error getting video length: {e}")
        return 0

def _build_transcript_api():
    """
    Build a YouTubeTranscriptApi instance with proxy support.

    Proxy is configured via environment variables:
    - Webshare rotating residential proxy:
        WEBSHARE_PROXY_USERNAME, WEBSHARE_PROXY_PASSWORD
    - Generic HTTP/HTTPS proxy:
        TRANSCRIPT_HTTP_PROXY, TRANSCRIPT_HTTPS_PROXY
    """
    import os
    from youtube_transcript_api import YouTubeTranscriptApi
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    webshare_user = os.environ.get('WEBSHARE_PROXY_USERNAME')
    webshare_pass = os.environ.get('WEBSHARE_PROXY_PASSWORD')
    http_proxy = os.environ.get('TRANSCRIPT_HTTP_PROXY')
    https_proxy = os.environ.get('TRANSCRIPT_HTTPS_PROXY')

    if webshare_user and webshare_pass:
        from youtube_transcript_api.proxies import WebshareProxyConfig
        print("  [Proxy] Using Webshare rotating residential proxy")
        return YouTubeTranscriptApi(
            proxy_config=WebshareProxyConfig(
                proxy_username=webshare_user,
                proxy_password=webshare_pass
            )
        )
    elif http_proxy or https_proxy:
        from youtube_transcript_api.proxies import GenericProxyConfig
        print(f"  [Proxy] Using generic proxy: {http_proxy or https_proxy}")
        return YouTubeTranscriptApi(
            proxy_config=GenericProxyConfig(
                http_url=http_proxy or https_proxy,
                https_url=https_proxy or http_proxy,
            )
        )
    else:
        return YouTubeTranscriptApi()


def get_transcript(video_id, max_retries=3):
    """Get transcript from YouTube video. Retries on 429 rate-limit errors."""
    import time

    def convert_to_json_serializable(item):
        """Convert FetchedTranscriptSnippet or similar objects to dicts."""
        if isinstance(item, dict):
            return item
        if hasattr(item, '_asdict'):
            return item._asdict()
        if hasattr(item, '__dict__'):
            return vars(item)
        try:
            return {
                'text': getattr(item, 'text', str(item)),
                'start': getattr(item, 'start', 0),
                'duration': getattr(item, 'duration', 0)
            }
        except:
            return str(item)

    def _fetch(api, video_id):
        try:
            transcript_list = api.list(video_id)
            transcript = transcript_list.find_transcript(['ko', 'en'])
            result = transcript.fetch()
            return [convert_to_json_serializable(item) for item in result]
        except Exception:
            transcript_list = api.list(video_id)
            transcript = transcript_list.find_generated_transcript(['ko', 'en'])
            result = transcript.fetch()
            return [convert_to_json_serializable(item) for item in result]

    for attempt in range(1, max_retries + 1):
        try:
            api = _build_transcript_api()
            return _fetch(api, video_id)
        except Exception as e:
            err_str = str(e)
            if 'Subtitles are disabled' in err_str:
                print(f"  [SKIP] Subtitles are disabled for video {video_id}")
                return 'subtitles_disabled'
            is_geo_blocked = (
                'not made this video available in your country' in err_str
                or ('unplayable' in err_str.lower() and 'country' in err_str.lower())
            )
            if is_geo_blocked:
                print(f"  [SKIP] Video not available in your country: {video_id}")
                return 'geo_blocked'
            is_rate_limit = '429' in err_str or 'too many' in err_str.lower()
            if is_rate_limit and attempt < max_retries:
                wait = 30 * attempt  # 30s, 60s, 90s
                print(f"  [429] Rate limited. Waiting {wait}s before retry {attempt}/{max_retries-1}...")
                time.sleep(wait)
            else:
                print(f"Error getting transcript: {e}")
                return None

def get_comments(video_url, sort_by=0, max_regular=50, max_timestamp=50):
    """
    Get comments from YouTube video.
    sort_by: 0 (Popular - 인기순), 1 (Recent - 최신순)
    """
    try:
        from youtube_comment_downloader import YoutubeCommentDownloader
        downloader = YoutubeCommentDownloader()
        
        generator = downloader.get_comments_from_url(video_url, sort_by=sort_by)
        
        timestamp_comments = []
        regular_comments = []
        
        max_scans_limit = 50000
        scanned_count = 0
        skipped_not_meaningful = 0
        skipped_no_timestamp = 0
        
        for comment in generator:
            # Skip reply comments (대댓글)
            if comment.get('reply'):
                continue

            scanned_count += 1
            if scanned_count > max_scans_limit:
                break

            comment_text = comment.get('text', '')
            timestamps = parse_timestamp(comment_text)
            
            # For timestamp comments, be more lenient with the meaningful comment check
            if timestamps:
                # Accept timestamp comments even if they're short
                if len(timestamp_comments) < max_timestamp:
                    # Just check that it's not empty
                    if comment_text.strip():
                        timestamp_comments.append({
                            **comment,
                            'timestamps_found': timestamps
                        })
            elif is_meaningful_comment(comment_text):
                if len(regular_comments) < max_regular:
                    regular_comments.append(comment)
            else:
                skipped_not_meaningful += 1
                        
            if len(timestamp_comments) >= max_timestamp and len(regular_comments) >= max_regular:
                break
        
        # Debug info
        if scanned_count > 0:
            print(f"  - Scanned: {scanned_count} comments")
            print(f"  - Timestamp comments: {len(timestamp_comments)}")
            print(f"  - Regular comments: {len(regular_comments)}")
            if skipped_not_meaningful > 0:
                print(f"  - Skipped (not meaningful): {skipped_not_meaningful}")
                
        return timestamp_comments, regular_comments, scanned_count
    except Exception as e:
        err_str = str(e)
        if 'not made this video available in your country' in err_str or 'unplayable' in err_str.lower() and 'country' in err_str.lower():
            print(f"  [SKIP] Video not available in your country")
            return 'geo_blocked', None, 0
        print(f"Error getting comments: {e}")
        return None, None, 0

def is_meaningful_comment(text):
    if not text:
        return False
        
    text_clean = re.sub(r'\s+', '', text)
    if len(text_clean) < 10:
        return False
        
    meaningful_chars = len(re.findall(r'[가-힣a-zA-Z0-9]', text))
    if meaningful_chars < 10:
        return False
        
    if meaningful_chars / len(text_clean) < 0.4:
        return False
        
    return True

def extract_video_id(url):
    patterns = [
        r'(?:youtube\.com\/watch\?v=|youtu\.be\/)([a-zA-Z0-9_-]{11})',
        r'youtube\.com\/embed\/([a-zA-Z0-9_-]{11})',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

def collect_video_data(video_url, max_regular=50, max_timestamp=50, sort_by=0):
    """Collects all required data for a single video."""
    video_id = extract_video_id(video_url)
    if not video_id:
        print(f"Error: Could not extract video ID from {video_url}")
        return {
            'video_url': video_url,
            'success': False,
            'error': 'Invalid video ID'
        }

    print(f"Processing video ID: {video_id}...")
    
    duration = get_video_length(video_url)
    transcript = get_transcript(video_id)

    if transcript in ('subtitles_disabled', 'geo_blocked'):
        return {
            'video_url': video_url,
            'video_id': video_id,
            'success': False,
            'error': transcript,
            'video_length': duration,
            'transcript': [],
            'timestamp_comments': [],
            'regular_comments': []
        }

    timestamp_comments, regular_comments, _ = get_comments(
        video_url, sort_by=sort_by, max_regular=max_regular, max_timestamp=max_timestamp
    )

    if timestamp_comments == 'geo_blocked':
        return {
            'video_url': video_url,
            'video_id': video_id,
            'success': False,
            'error': 'geo_blocked',
            'video_length': duration,
            'transcript': transcript if transcript else [],
            'timestamp_comments': [],
            'regular_comments': []
        }

    success = transcript is not None and timestamp_comments is not None and regular_comments is not None

    return {
        'video_url': video_url,
        'video_id': video_id,
        'success': success,
        'video_length': duration,
        'transcript': transcript if transcript else [],
        'timestamp_comments': timestamp_comments if timestamp_comments else [],
        'regular_comments': regular_comments if regular_comments else []
    }

def main():
    parser = argparse.ArgumentParser(description="YouTube Data Collector")
    parser.add_argument("url", help="YouTube video URL")
    parser.add_argument("--max-comments", "-m", type=int, default=50,
                        help="Maximum number of comments to collect (default: 50)")
    parser.add_argument("--sort-by", "-s", type=int, choices=[0, 1], default=0,
                        help="Sort comments by: 0 for Popular, 1 for Recent (default: 0)")
    parser.add_argument("--output", "-o", default="output.jsonl", help="Output JSONL file")
    
    args = parser.parse_args()
    
    data = collect_video_data(args.url, max_regular=args.max_comments, sort_by=args.sort_by)
    
    with open(args.output, 'a', encoding='utf-8') as f:
        f.write(json.dumps(data, ensure_ascii=False) + '\n')
    
    if data['success']:
        print(f"✓ Data successfully saved to {args.output}")
    else:
        print("✗ Failed to collect complete data")

if __name__ == "__main__":
    main()
