# Hi-VideoSum

> A User-Centric YouTube Video Summarization & Highlight Service for Korean
>
> Sungkyunkwan University · AI Convergence · Data Science Capstone (2026)

Hi-VideoSum은 **영상 프레임을 보지 않고** 두 가지 텍스트 신호—**자막(transcript)** 과 **시청자 댓글(comments)** —만으로 한국어 유튜브 영상을 3문단 산문으로 요약하는 sLLM 기반 서비스입니다.

- 📄 **Dataset:** [`kim586w/hivideosum_training_dataset`](https://huggingface.co/datasets/kim586w/hivideosum_training_dataset)
- 🌐 **Project page:** [`docs/page/index.html`](docs/page/index.html)
- 📝 **Mid-term report:** [`docs/report/main.tex`](docs/report/main.tex)

---

## Repository layout

```
hivideosum/
├── data/                              # Dataset construction pipeline
│   ├── crawl_raw_data/                # Step 1–2 — channel curation, transcript & comment scrape
│   ├── filter_kexaone/                # Step 3–4 — K-EXAONE 3-axis comment filtering
│   └── summarize/                     # Step 5    — Gemini / EXAONE / K-EXAONE label generation
├── training/
│   └── gemma_lora/                    # Step 6    — gemma-4-E4B-it LoRA fine-tuning
├── service/
│   ├── backend/                       # FastAPI + arq worker + vLLM serving
│   └── extension/                     # Chrome MV3 extension (YouTube watch-page sidebar)
└── docs/
    ├── page/                          # Static project landing page (index.html)
    └── report/                        # LaTeX mid-term report (XeLaTeX)
```

Each leaf directory keeps its own `README.md` with run instructions; the per-module READMEs are authoritative for execution.

---

## End-to-end pipeline

```
┌────────────────────────── data/ ──────────────────────────┐    ┌── training/ ──┐    ┌────── service/ ──────┐
│                                                            │    │                │    │                       │
│  crawl_raw_data ──► filter_kexaone ──► summarize           │ ─► │  gemma_lora    │ ─► │  backend (vLLM+API)   │
│  (yt-dlp,            (Elice K-EXAONE     (Gemini / EXAONE   │    │  LoRA r=32,    │    │  + extension (Chrome) │
│   yt-transcript-api,  3-axis 1–3)         3-paragraph       │    │  α=64,         │    │                       │
│   yt-comment-dl)                          prose labels)     │    │  bf16, seq 20k)│    │                       │
└────────────────────────────────────────────────────────────┘    └────────────────┘    └───────────────────────┘
```

| # | Stage | Where | Output |
|---|-------|-------|--------|
| 1 | Channel curation                       | `data/crawl_raw_data/inputs/channels.jsonl` | ≈80 Korean channels, 7 top-level + 16 sub-categories |
| 2 | Raw collection (transcript + comments) | `data/crawl_raw_data/`                       | `combined_data.jsonl` per channel                       |
| 3 | Rule-based filter (regex, ratio)       | `data/crawl_raw_data/`                       | timestamped vs general comments split                   |
| 4 | 3-axis LLM filter (info / opinion / relevance ≥ 6) | `data/filter_kexaone/`           | `filtered_comments_kexaone.jsonl`                       |
| 5 | 3-paragraph prose label generation     | `data/summarize/`                            | `summarized_data_gemini.jsonl` (training labels)        |
| 6 | sLLM LoRA fine-tune                    | `training/gemma_lora/`                       | `output/adapter_model.safetensors`                      |
| 7 | Web service (FastAPI + arq + vLLM)     | `service/backend/`                           | `POST /jobs` → 30–120s → 3-paragraph summary            |
| 8 | Chrome extension (sidebar on YouTube)  | `service/extension/`                         | DOM-injected `#hvs-panel` calling the backend           |

---

## Authors

Yeon-hu Jung · Kyeong-jun Oh · Yong-ha Lee · Kipyo Kim

Advisor: Mina Jung — Sungkyunkwan University, AI Convergence

---

## Citation

```bibtex
@misc{hivideosum2026,
  title       = {Hi-VideoSum: A User-Centric YouTube Video Summarization and Highlight Service for Korean},
  author      = {Jung, Yeon-hu and Oh, Kyeong-jun and Lee, Yong-ha and Kim, Kipyo},
  institution = {Sungkyunkwan University, AI Convergence},
  advisor     = {Jung, Mina},
  course      = {Data Science Capstone Project},
  year        = {2026},
  note        = {Mid-term report, v0.2},
  url         = {https://huggingface.co/datasets/kim586w/hivideosum_training_dataset}
}
```
