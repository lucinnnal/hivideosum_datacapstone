#!/usr/bin/env python3
"""
Summarize YouTube Video Data with Gemini 2.5
Reads combined_data.jsonl and generates video summaries for sLLM training.
"""

import json
import os
import sys
import argparse
import time
from dotenv import load_dotenv

load_dotenv()

try:
    from google import genai
    from google.genai import types
except ImportError:
    print("Please install google-genai: pip install google-genai")
    sys.exit(1)

def build_prompt(transcript, timestamp_comments, regular_comments):
    # Truncate to avoid exceeding context window limits
    # Transcripts can be very long
    transcript_text = " ".join([item.get('text', '') for item in transcript])
    
    # Get top comments
    tc_text = "\n".join([f"- {c.get('text', '').strip()}" for c in timestamp_comments[:50]])
    rc_text = "\n".join([f"- {c.get('text', '').strip()}" for c in regular_comments[:100]])
    
    prompt = f"""
당신은 유튜브 비디오의 트랜스크립트(자막)와 시청자 댓글을 분석하여 고품질의 요약 데이터를 생성하는 AI 전문가입니다.
제공된 트랜스크립트와 시청자 댓글(타임스탬프 댓글 및 일반 댓글)을 바탕으로 비디오에 대한 전반적인 요약, 하이라이트, 그리고 시청자 반응을 종합적으로 정리해주세요. 이 결과물은 추후 sLLM 모델 튜닝을 위한 고품질 학습 데이터로 사용될 예정입니다.

다음 구조를 따라 한국어로 답변을 작성해주세요:
1. **비디오 핵심 요약 (Overview)**: 이 영상이 어떤 내용을 다루고 있는지 3-4문장으로 요약하세요.
2. **주요 하이라이트 (Key Highlights)**: 영상의 핵심 내용이나 타임스탬프 댓글에서 자주 언급되는 중요한 부분들을 글머리 기호(bullet points)로 정리하세요.
3. **시청자 반응 요약 (Viewer Reactions)**: 댓글들을 분석하여 시청자들이 어떤 점에 공감하거나 반응했는지, 주된 여론이나 재미있는 포인트는 무엇인지 정리하세요.

[입력 데이터]
- 트랜스크립트(자막) 일부:
{transcript_text[:15000]}... (생략됨)

- 타임스탬프 기반 주요 댓글:
{tc_text}

- 일반 시청자 댓글:
{rc_text}
"""
    return prompt.strip()

def main():
    parser = argparse.ArgumentParser(description="Generate summaries using Gemini 2.5")
    parser.add_argument("input_file", help="Input JSONL file (combined_data.jsonl)")
    parser.add_argument("--output", "-o", default="gemini_results_for_training.jsonl", help="Output JSONL file")
    parser.add_argument("--model", "-m", default="gemini-2.5-flash", help="Gemini model to use (default: gemini-2.5-flash). Overridden by config if provided.")
    parser.add_argument("--config", "-c", default="generation_configs/gemini.json", help="Path to Gemini config file")
    
    args = parser.parse_args()
    
    # Load Gemini config
    gemini_config = {}
    if os.path.exists(args.config):
        with open(args.config, 'r', encoding='utf-8') as f:
            gemini_config = json.load(f)
    else:
        print(f"Warning: Config file {args.config} not found. Using defaults.")
        
    model_name = gemini_config.get("model_name", args.model)
    gen_config_params = gemini_config.get("generation_config", {})
    
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY environment variable is not set.")
        print("Please export it: export GEMINI_API_KEY='your_api_key'")
        sys.exit(1)
        
    client = genai.Client(api_key=api_key)
    
    if not os.path.exists(args.input_file):
        print(f"Error: {args.input_file} not found.")
        sys.exit(1)
        
    # Read existing processed records to avoid re-running if restarted
    processed_urls = set()
    if os.path.exists(args.output):
        with open(args.output, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    data = json.loads(line)
                    if 'video_url' in data:
                        processed_urls.add(data['video_url'])
                except:
                    pass

    with open(args.input_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
    print(f"Loaded {len(lines)} records from {args.input_file}")
    
    with open(args.output, 'a', encoding='utf-8') as f_out:
        for idx, line in enumerate(lines, 1):
            if not line.strip():
                continue
                
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
                
            video_url = data.get('video_url')
            
            if not data.get('success'):
                print(f"[{idx}/{len(lines)}] Skipping failed collection for {video_url}")
                continue
                
            if video_url in processed_urls:
                print(f"[{idx}/{len(lines)}] Skipping already processed video: {video_url}")
                continue
                
            print(f"[{idx}/{len(lines)}] Processing video: {video_url}")
            
            prompt = build_prompt(
                data.get('transcript', []), 
                data.get('timestamp_comments', []), 
                data.get('regular_comments', [])
            )
            
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(**gen_config_params) if gen_config_params else None,
                )
                
                summary_text = response.text
                
                result_data = {
                    'video_url': video_url,
                    'video_id': data.get('video_id'),
                    'video_length': data.get('video_length'),
                    'prompt': prompt,
                    'gemini_summary': summary_text
                }
                
                f_out.write(json.dumps(result_data, ensure_ascii=False) + '\n')
                f_out.flush()
                print("  ✓ Summary generated successfully.")
                
                # Sleep briefly to avoid aggressive rate limiting
                time.sleep(2)
                
            except Exception as e:
                print(f"  ✗ Error generating summary: {e}")

if __name__ == "__main__":
    main()
