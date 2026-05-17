import json
import os
from datetime import date

MISMATCH_LOG_PATH = 'data/mismatch_log.json'


def load_filtered(path: str) -> dict:
    """filtered_comments JSONL에서 video_url별 댓글 수를 반환한다.

    Args:
        path: filtered_comments_kexaone_kkp.jsonl 경로.

    Returns:
        {video_url: {'general_count': int, 'timestamp_count': int}} 형태의 dict.
    """
    result = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            er = obj.get('evaluation_result', {})
            result[obj['video_url']] = {
                'general_count': len(er.get('general_comments', [])),
                'timestamp_count': len(er.get('timestamp_comments', []))
            }
    return result


def load_combined(path: str) -> dict:
    """combined_data JSONL에서 video_url별 댓글 수를 반환한다.

    Args:
        path: combined_data_no_overlap_merged.jsonl 경로.

    Returns:
        {video_url: {'regular_count': int, 'timestamp_count': int}} 형태의 dict.
    """
    result = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            result[obj['video_url']] = {
                'regular_count': len(obj.get('regular_comments', [])),
                'timestamp_count': len(obj.get('timestamp_comments', []))
            }
    return result


def compare(filtered: dict, combined: dict) -> dict:
    """두 dict를 비교해 불일치 항목을 분류한다.

    Args:
        filtered: load_filtered() 결과.
        combined: load_combined() 결과.

    Returns:
        {
            'match': int,
            'mismatch_general': list,
            'mismatch_timestamp': list,
            'mismatch_both': list,
            'not_found': list
        }
    """
    mismatch_general = []
    mismatch_timestamp = []
    mismatch_both = []
    not_found = []

    for url, fc in filtered.items():
        if url not in combined:
            not_found.append(url)
            continue
        cc = combined[url]
        gen_diff = fc['general_count'] != cc['regular_count']
        ts_diff = fc['timestamp_count'] != cc['timestamp_count']
        entry = {
            'url': url,
            'filtered_general': fc['general_count'],
            'combined_regular': cc['regular_count'],
            'filtered_timestamp': fc['timestamp_count'],
            'combined_timestamp': cc['timestamp_count']
        }
        if gen_diff and ts_diff:
            mismatch_both.append(entry)
        elif gen_diff:
            mismatch_general.append(entry)
        elif ts_diff:
            mismatch_timestamp.append(entry)

    total_mismatch = len(mismatch_general) + len(mismatch_timestamp) + len(mismatch_both)
    return {
        'match': len(filtered) - total_mismatch - len(not_found),
        'mismatch_general': mismatch_general,
        'mismatch_timestamp': mismatch_timestamp,
        'mismatch_both': mismatch_both,
        'not_found': not_found
    }


def load_mismatch_log(path: str) -> dict:
    """기존 불일치 로그를 불러온다.

    Args:
        path: mismatch_log.json 경로.

    Returns:
        {video_url: 로그 항목} 형태의 dict. 파일이 없으면 빈 dict.
    """
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f)


def update_mismatch_log(result: dict, log_path: str) -> tuple[int, int, int]:
    """불일치 결과를 로그 파일에 반영한다.

    - 신규 불일치 url은 추가한다.
    - 기존에 기록된 url이 이번에도 불일치면 last_seen과 counts를 갱신한다.
    - 기존에 기록된 url이 이번에 일치로 바뀌었으면 resolved=true로 표시한다.

    Args:
        result: compare() 결과.
        log_path: mismatch_log.json 경로.

    Returns:
        (신규 추가 수, 갱신 수, 해소 수) 튜플.
    """
    today = date.today().isoformat()
    log = load_mismatch_log(log_path)

    type_map = {}
    for entry in result['mismatch_general']:
        type_map[entry['url']] = ('general_only', entry)
    for entry in result['mismatch_timestamp']:
        type_map[entry['url']] = ('timestamp_only', entry)
    for entry in result['mismatch_both']:
        type_map[entry['url']] = ('both', entry)
    for url in result['not_found']:
        type_map[url] = ('not_found', {'url': url,
                                        'filtered_general': None,
                                        'combined_regular': None,
                                        'filtered_timestamp': None,
                                        'combined_timestamp': None})

    added = updated = removed = 0

    for url, (mtype, entry) in type_map.items():
        if url not in log:
            log[url] = {
                'video_url': url,
                'mismatch_type': mtype,
                'filtered_general': entry['filtered_general'],
                'combined_regular': entry['combined_regular'],
                'filtered_timestamp': entry['filtered_timestamp'],
                'combined_timestamp': entry['combined_timestamp'],
                'first_seen': today,
                'last_seen': today,
                'resolved': False
            }
            added += 1
        else:
            prev = log[url]
            changed = (
                prev.get('filtered_general') != entry['filtered_general'] or
                prev.get('filtered_timestamp') != entry['filtered_timestamp'] or
                prev.get('resolved') is True
            )
            log[url].update({
                'mismatch_type': mtype,
                'filtered_general': entry['filtered_general'],
                'combined_regular': entry['combined_regular'],
                'filtered_timestamp': entry['filtered_timestamp'],
                'combined_timestamp': entry['combined_timestamp'],
                'last_seen': today,
                'resolved': False
            })
            if changed:
                updated += 1

    for url in [u for u in log if u not in type_map]:
        del log[url]
        removed += 1

    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, 'w') as f:
        json.dump(log, f, ensure_ascii=False, indent=2)

    return added, updated, removed


def print_report(filtered: dict, result: dict) -> None:
    """비교 결과를 출력한다.

    Args:
        filtered: load_filtered() 결과 (전체 url 수 계산용).
        result: compare() 결과.
    """
    total_mismatch = (
        len(result['mismatch_general']) +
        len(result['mismatch_timestamp']) +
        len(result['mismatch_both'])
    )

    print(f"filtered video_url 수 : {len(filtered)}")
    print(f"완전 일치             : {result['match']}개")
    print(f"불일치 합계           : {total_mismatch}개")
    print(f"  일반 댓글만 불일치  : {len(result['mismatch_general'])}개")
    print(f"  timestamp만 불일치  : {len(result['mismatch_timestamp'])}개")
    print(f"  둘 다 불일치        : {len(result['mismatch_both'])}개")
    print(f"combined에 없는 url   : {len(result['not_found'])}개")

    def _detail(label, items):
        if not items:
            return
        print(f"\n[{label}]")
        for item in items:
            print(f"  {item['url']}")
            print(f"    general  : filtered={item['filtered_general']}, combined={item['combined_regular']}")
            print(f"    timestamp: filtered={item['filtered_timestamp']}, combined={item['combined_timestamp']}")

    _detail("일반 댓글만 불일치", result['mismatch_general'])
    _detail("timestamp만 불일치", result['mismatch_timestamp'])
    _detail("둘 다 불일치", result['mismatch_both'])

    if result['not_found']:
        print("\n[combined에 없는 url]")
        for u in result['not_found']:
            print(f"  {u}")


if __name__ == '__main__':
    filtered = load_filtered('data/filtered_comments_kexaone_kkp.jsonl')
    combined = load_combined('data/combined_data_no_overlap_merged.jsonl')
    result = compare(filtered, combined)
    print_report(filtered, result)

    added, updated, removed = update_mismatch_log(result, MISMATCH_LOG_PATH)
    print(f"\n[mismatch_log.json 업데이트]")
    print(f"  신규 추가     : {added}개")
    print(f"  수치 갱신     : {updated}개")
    print(f"  로그에서 제거 : {removed}개")
    print(f"  저장 경로     : {MISMATCH_LOG_PATH}")
