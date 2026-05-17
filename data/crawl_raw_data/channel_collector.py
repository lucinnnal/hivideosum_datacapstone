#!/usr/bin/env python3
"""
YouTube Channel Video Collector
Given a list of YouTube channel URLs, fetches the latest N videos per channel
and collects transcript + comments data for each video.
"""

import json
import os
import sys
import time
import argparse
from datetime import datetime


VIDEO_LOG_FILE = "video_log.json"


def load_video_log(log_path):
    """Load per-video status log. Returns dict keyed by video_id."""
    if os.path.exists(log_path):
        with open(log_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def update_video_log(log_path, log, video_id, video_url, title, channel_name, channel_url, status, detail=""):
    """Update a single video entry in the log and save."""
    log[video_id] = {
        'video_url': video_url,
        'title': title,
        'channel_name': channel_name,
        'channel_url': channel_url,
        'status': status,           # 'collected' | 'skipped' | 'error'
        'timestamp': datetime.now().isoformat(),
        'detail': detail,
    }
    with open(log_path, 'w', encoding='utf-8') as f:
        json.dump(log, f, ensure_ascii=False, indent=2)

def _is_valid_video_id(video_id):
    """Check if a string looks like a valid YouTube video ID (11 chars, alphanumeric + _ -)."""
    import re
    return bool(re.fullmatch(r'[a-zA-Z0-9_-]{11}', video_id))


def get_channel_videos(channel_url, fetch_limit=200):
    """
    Use yt-dlp to fetch videos from a YouTube channel.
    - Filters to only videos with duration 5-30 minutes (300-1800 seconds).
    - Sorts by comment_count descending; falls back to view_count if unavailable.
    Returns a list of dicts with video metadata.
    """
    import yt_dlp

    clean_url = channel_url.rstrip('/')
    if not clean_url.endswith('/videos'):
        clean_url += '/videos'

    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': True,
        'playlistend': fetch_limit,
        'nocheckcertificate': True,
    }

    videos = []
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(clean_url, download=False)

            if info is None:
                print(f"  Warning: Could not extract info from {clean_url}")
                return []

            entries = info.get('entries', []) or []

            for entry in entries:
                if entry is None:
                    continue
                video_id = entry.get('id') or entry.get('url')
                if not video_id:
                    continue

                if not _is_valid_video_id(video_id):
                    continue

                duration = entry.get('duration') or 0

                # Filter: only 5-30 minute videos (300-1800 seconds)
                if not (300 <= duration <= 1800):
                    continue

                video_url = f"https://www.youtube.com/watch?v={video_id}"
                videos.append({
                    'url': video_url,
                    'title': entry.get('title', ''),
                    'upload_date': entry.get('upload_date', ''),
                    'duration': duration,
                    'comment_count': entry.get('comment_count'),  # may be None
                    'view_count': entry.get('view_count') or 0,
                })

    except Exception as e:
        print(f"  Error fetching channel videos: {e}")

    # Sort by comment_count if available, otherwise by view_count
    has_comment_count = any(v['comment_count'] is not None for v in videos)
    if has_comment_count:
        videos.sort(key=lambda v: (v['comment_count'] or 0), reverse=True)
        print(f"  Sorted {len(videos)} eligible videos by comment count")
    else:
        videos.sort(key=lambda v: v['view_count'], reverse=True)
        print(f"  Sorted {len(videos)} eligible videos by view count (comment count unavailable)")

    return videos


def load_channels(jsonl_file):
    """
    Load channel entries from a JSONL file.
    Each line should be JSON with at least a 'channel_url' field.
    Alternatively, 'url' or 'channel' fields are also accepted.
    """
    channels = []
    with open(jsonl_file, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                url = (
                    data.get('channel_url')
                    or data.get('url')
                    or data.get('channel')
                )
                if url:
                    channels.append({
                        'channel_url': url,
                        'channel_name': data.get('channel_name', data.get('name', '')),
                        'line': line_num,
                    })
                else:
                    print(f"Warning: No channel URL found in line {line_num}")
            except json.JSONDecodeError as e:
                print(f"Warning: Invalid JSON at line {line_num}: {e}")
    return channels


CHANNEL_VIDEO_TARGET = 300     # videos to collect per channel
MIN_REGULAR_PER_VIDEO = 5      # minimum regular comments required per video
MIN_TIMESTAMP_PER_VIDEO = 5    # minimum timestamp comments required per video


def main():
    parser = argparse.ArgumentParser(
        description="Collect YouTube data from a list of channels"
    )
    parser.add_argument("channels_file", help="Input JSONL file with channel URLs")
    parser.add_argument("--output-dir", "-o", default="output_dir",
                        help="Output directory (default: output_dir)")
    parser.add_argument("--fetch-limit", "-n", type=int, default=300,
                        help="Max videos to fetch per channel for filtering/sorting (default: 300)")
    parser.add_argument("--max-comments", "-m", type=int, default=100,
                        help="Max comments to collect per video (default: 100)")

    args = parser.parse_args()

    print("=" * 60)
    print("YouTube Channel Data Collector")
    print("=" * 60)
    print(f"Channels file      : {args.channels_file}")
    print(f"Output dir         : {args.output_dir}")
    print(f"Fetch limit/channel: {args.fetch_limit} videos")
    print(f"Max comments/video : {args.max_comments}")
    print(f"Target/channel     : {CHANNEL_VIDEO_TARGET} videos")
    print(f"Min per video      : {MIN_REGULAR_PER_VIDEO} regular, {MIN_TIMESTAMP_PER_VIDEO} timestamp")
    print(f"Video duration     : 5-30 minutes")
    print(f"Started at         : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    print()

    channels = load_channels(args.channels_file)
    if not channels:
        print("No channels found in the input file.")
        sys.exit(1)

    print(f"Found {len(channels)} channel(s) to process\n")

    os.makedirs(args.output_dir, exist_ok=True)

    import youtube_collector

    combined_output = os.path.join(args.output_dir, "combined_data.jsonl")
    urls_file = os.path.join(args.output_dir, "urls.jsonl")
    log_path = os.path.join(args.output_dir, VIDEO_LOG_FILE)

    # Load per-video log (collected / skipped / error)
    video_log = load_video_log(log_path)
    done_ids = {vid for vid, entry in video_log.items() if entry['status'] in ('collected', 'skipped')}
    print(f"Video log loaded: {len(video_log)} entries "
          f"(collected={sum(1 for e in video_log.values() if e['status']=='collected')}, "
          f"skipped={sum(1 for e in video_log.values() if e['status']=='skipped')}, "
          f"error={sum(1 for e in video_log.values() if e['status']=='error')})")
    print(f"Resuming: {len(done_ids)} video(s) will be skipped (collected or skipped)\n")

    success_channels = 0
    skipped_channels = 0
    total_videos_written = 0

    with open(combined_output, 'a', encoding='utf-8') as f_out, \
         open(urls_file, 'a', encoding='utf-8') as f_urls:

        for ch_idx, ch in enumerate(channels, 1):
            channel_url = ch['channel_url']
            channel_name = ch.get('channel_name', f'channel_{ch_idx}')

            print(f"\n{'=' * 60}")
            print(f"[{ch_idx}/{len(channels)}] {channel_name}")
            print(f"  URL: {channel_url}")

            # Phase 1: Fetch, filter (5-30 min), and sort videos
            videos = get_channel_videos(channel_url, fetch_limit=args.fetch_limit)

            if not videos:
                print(f"  -> SKIPPED: No eligible videos (5-30 min) found")
                skipped_channels += 1
                continue

            # Write eligible video URLs
            for v in videos:
                f_urls.write(json.dumps({
                    'url': v['url'],
                    'title': v.get('title', ''),
                    'channel_name': channel_name,
                    'channel_url': channel_url,
                    'duration': v.get('duration'),
                    'comment_count': v.get('comment_count'),
                    'view_count': v.get('view_count'),
                }, ensure_ascii=False) + '\n')

            # Phase 2: Collect comments per video until channel target is reached
            channel_videos = 0

            for v_idx, v in enumerate(videos, 1):
                if channel_videos >= CHANNEL_VIDEO_TARGET:
                    break

                url = v['url']
                title = v.get('title', '')
                dur_min = int(v.get('duration') or 0) // 60
                dur_sec = int(v.get('duration') or 0) % 60
                print(f"\n  [{v_idx}/{len(videos)}] {title} ({dur_min}:{dur_sec:02d})")
                print(f"    URL: {url}")

                video_id = url.split('v=')[-1].split('&')[0]

                if video_id in done_ids:
                    status = video_log.get(video_id, {}).get('status', '?')
                    print(f"    -> SKIP (log: {status})")
                    if status == 'collected':
                        channel_videos += 1  # count toward channel target
                    continue

                MAX_RETRIES = 3
                data = None
                last_error = None

                for attempt in range(1, MAX_RETRIES + 1):
                    try:
                        data = youtube_collector.collect_video_data(
                            video_url=url,
                            max_regular=args.max_comments,
                            max_timestamp=args.max_comments,
                            sort_by=0,  # sort by popularity
                        )
                        data['channel_name'] = channel_name
                        data['channel_url'] = channel_url
                        data['title'] = title

                        if not data.get('success', False):
                            last_error = data.get('error', 'transcript or comments collection failed')
                            if last_error in ('subtitles_disabled', 'geo_blocked'):
                                print(f"    -> SKIPPED: {last_error}")
                                update_video_log(log_path, video_log, video_id, url, title,
                                                 channel_name, channel_url, 'skipped', last_error)
                                done_ids.add(video_id)
                                data = None
                                break
                            print(f"    -> [{attempt}/{MAX_RETRIES}] 실패: {last_error}")
                            if attempt < MAX_RETRIES:
                                print(f"    -> 10초 후 재시도 ({attempt+1}/{MAX_RETRIES})...")
                                time.sleep(10)
                            data = None
                            continue

                        last_error = None
                        break  # 성공

                    except Exception as e:
                        last_error = str(e)
                        is_geo_blocked = (
                            'not made this video available in your country' in last_error
                            or ('unplayable' in last_error.lower() and 'country' in last_error.lower())
                        )
                        if is_geo_blocked:
                            print(f"    -> SKIPPED: geo_blocked (country restriction)")
                            update_video_log(log_path, video_log, video_id, url, title,
                                             channel_name, channel_url, 'skipped', 'geo_blocked')
                            done_ids.add(video_id)
                            data = None
                            last_error = 'geo_blocked'
                            break
                        print(f"    -> [{attempt}/{MAX_RETRIES}] 오류: {last_error}")
                        if attempt < MAX_RETRIES:
                            print(f"    -> 10초 후 재시도 ({attempt+1}/{MAX_RETRIES})...")
                            time.sleep(10)
                        data = None

                if data is None and last_error in ('subtitles_disabled', 'geo_blocked'):
                    pass  # already logged as skipped above
                elif data is None:
                    print(f"    -> ERROR (3회 모두 실패): {last_error}")
                    update_video_log(log_path, video_log, video_id, url, title,
                                     channel_name, channel_url, 'error', last_error)
                    # error는 done_ids에 추가하지 않음 → 다음 세션에서 재시도 가능
                else:
                    tc = len(data.get('timestamp_comments', []))
                    rc = len(data.get('regular_comments', []))

                    # Skip video if it doesn't meet minimum comment thresholds
                    if rc < MIN_REGULAR_PER_VIDEO or tc < MIN_TIMESTAMP_PER_VIDEO:
                        detail = (f"regular={rc}, timestamp={tc} "
                                  f"(need >= {MIN_REGULAR_PER_VIDEO} each)")
                        print(f"    -> SKIPPED: {detail}")
                        update_video_log(log_path, video_log, video_id, url, title,
                                         channel_name, channel_url, 'skipped', detail)
                        done_ids.add(video_id)
                    else:
                        f_out.write(json.dumps(data, ensure_ascii=False) + '\n')
                        f_out.flush()
                        channel_videos += 1
                        total_videos_written += 1
                        tr = len(data.get('transcript', []))
                        detail = f"regular={rc}, timestamp={tc}, transcript={tr}"
                        print(f"    -> COLLECTED: {detail} | channel videos={channel_videos}")
                        update_video_log(log_path, video_log, video_id, url, title,
                                         channel_name, channel_url, 'collected', detail)
                        done_ids.add(video_id)

                time.sleep(10)  # YouTube IP 차단 방지용 요청 간격

            if channel_videos == 0:
                print(f"\n  -> CHANNEL SKIPPED: no videos passed the minimum thresholds")
                skipped_channels += 1
                continue

            print(f"\n  -> CHANNEL OK: {channel_videos} videos collected"
                  + (f" (target {CHANNEL_VIDEO_TARGET} reached)" if channel_videos >= CHANNEL_VIDEO_TARGET else f" (all available, under target {CHANNEL_VIDEO_TARGET})"))
            success_channels += 1

    # Summary
    print("\n" + "=" * 60)
    print("COLLECTION COMPLETE")
    print("=" * 60)
    print(f"Channels processed : {len(channels)}")
    print(f"  Collected        : {success_channels}")
    print(f"  Skipped          : {skipped_channels}")
    print(f"Videos written     : {total_videos_written}")
    print(f"\nOutput files in '{args.output_dir}/':")
    print(f"  - urls.jsonl              (eligible video URL list)")
    print(f"  - combined_data.jsonl     (raw collected data)")
    print(f"  - video_log.json          (per-video status: collected/skipped/error)")

    log_file = os.path.join(args.output_dir, 'collection_log.json')
    with open(log_file, 'w', encoding='utf-8') as f:
        json.dump({
            'timestamp': datetime.now().isoformat(),
            'channels_file': args.channels_file,
            'channels_count': len(channels),
            'channels_collected': success_channels,
            'channels_skipped': skipped_channels,
            'videos_written': total_videos_written,
            'channel_video_target': CHANNEL_VIDEO_TARGET,
            'min_regular_per_video': MIN_REGULAR_PER_VIDEO,
            'min_timestamp_per_video': MIN_TIMESTAMP_PER_VIDEO,
        }, f, ensure_ascii=False, indent=2)
    print(f"  - collection_log.json     (run summary)")
    print(f"\nFinished at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    main()
