# gemma-4-E4B-it LoRA Fine-tuning

`google/gemma-4-E4B-it`을 유튜브 영상 요약 태스크에 대해 LoRA로 파인튜닝하는 스크립트입니다.

학습 데이터셋은 HuggingFace Hub에서 확인할 수 있습니다: [kim586w/hivideosum_training_dataset](https://huggingface.co/datasets/kim586w/hivideosum_training_dataset)

---

## 환경 요구사항

| 항목 | 요구사항 |
|------|---------|
| OS | Linux (Ubuntu 22.04+ 권장) |
| GPU | A100 80 GB (bf16 전체 정밀도 학습) |
| CUDA Driver | **12.8** |
| Python | 3.10 – 3.12 |

---

## 환경 설정

### 1. Python 가상환경 생성

```bash
python -m venv .venv
source .venv/bin/activate
```

### 2. PyTorch 설치 (CUDA 12.8 전용 빌드)

```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128
```

> `torch.cuda.is_available()` 이 `True`인지 반드시 확인하세요.

### 3. 나머지 의존성 설치

```bash
pip install -r requirements.txt
```

### 4. 환경 변수 설정 (W&B API 키)

`.env.example`을 복사하여 `.env`를 만들고 실제 키를 입력합니다.

```bash
cp .env.example .env
# .env 열어서 WANDB_API_KEY 값 입력
```

```
WANDB_API_KEY=your_wandb_api_key_here
```

> W&B API 키는 https://wandb.ai/authorize 에서 확인할 수 있습니다.  
> `.env`는 `.gitignore`에 등록되어 있어 실수로 커밋되지 않습니다.

### 5. HuggingFace 로그인 (gated 모델 접근용)

```bash
huggingface-cli login
```

---

## 학습 실행

### 로컬 실행

```bash
bash run_train.sh                          # config.yaml 사용
bash run_train.sh --config my_exp.yaml     # 커스텀 config 지정
```

---

## 하이퍼파라미터 설정 (`config.yaml`)

모든 하이퍼파라미터는 `config.yaml` 한 곳에서 관리합니다.

```yaml
# 모델 & 데이터
model_id: "google/gemma-4-E4B-it"
dataset_id: "kim586w/hivideosum_training_dataset"
output_dir: "./output"

# LoRA
lora:
  r: 32           # rank — 높을수록 표현력 ↑, 메모리 ↑
  alpha: 64       # scaling = alpha / r
  dropout: 0.05
  target_modules: [q_proj, k_proj, v_proj, o_proj, gate_proj, up_proj, down_proj]

# Training
training:
  num_train_epochs: 3
  per_device_train_batch_size: 4
  gradient_accumulation_steps: 2   # effective batch = 4 × 2 = 8
  learning_rate: 2e-4
  lr_scheduler_type: cosine
  warmup_ratio: 0.03
  optim: adamw_torch_fused
  max_seq_length: 4096
  ...
```

| 키 | 기본값 | 설명 |
|----|--------|------|
| `model_id` | `google/gemma-4-E4B-it` | 베이스 모델 HuggingFace ID |
| `dataset_id` | [`kim586w/hivideosum_training_dataset`](https://huggingface.co/datasets/kim586w/hivideosum_training_dataset) | 학습 데이터셋 |
| `output_dir` | `./output` | 체크포인트 저장 경로 |
| `lora.r` | `32` | LoRA rank |
| `lora.alpha` | `64` | LoRA scaling (보통 r × 2) |
| `lora.dropout` | `0.05` | LoRA dropout |
| `training.num_train_epochs` | `3` | 학습 에폭 수 |
| `training.per_device_train_batch_size` | `4` | GPU당 배치 크기 |
| `training.gradient_accumulation_steps` | `2` | 유효 배치 = batch × accum |
| `training.learning_rate` | `2e-4` | 최대 학습률 |
| `training.max_seq_length` | `4096` | 최대 토큰 길이 |

---

## 코드 작동 방식

### `train_lora.py`

```
1. config.yaml 로드 (--config 인자로 경로 지정 가능)

2. Tokenizer 로드
      └─ AutoTokenizer (pad_token 없으면 eos_token으로 대체)

3. 데이터셋 로드 & 전처리
      └─ HuggingFace Hub에서 dataset_id 로드
      └─ messages 필드(system/user/assistant 3턴)에 chat template 적용
      └─ 결과를 "text" 컬럼 하나만 남기는 형태로 변환

4. 모델 로드 (bf16 전체 정밀도 — A100 80 GB)
      └─ torch_dtype=bfloat16: 양자화 없이 full precision 학습
      └─ device_map="auto" → 멀티 GPU 자동 분산
      └─ attn_implementation="sdpa" → PyTorch SDPA 기반 효율적 어텐션

5. 멀티모달 타워 동결
      └─ language_model / lm_head 이외의 파라미터 requires_grad=False
      └─ 비전·오디오 인코더는 학습에서 제외

6. LoRA 어댑터 적용
      └─ config.yaml의 lora 섹션 값으로 LoraConfig 구성
      └─ get_peft_model → 전체 파라미터 중 약 0.1~0.3%만 학습

7. SFTTrainer 학습
      └─ config.yaml의 training 섹션 값으로 SFTConfig 구성
      └─ adamw_torch_fused: A100 Tensor Core 최적화 AdamW
      └─ cosine LR 스케줄러 + warmup 3%
      └─ gradient_checkpointing: 활성화 재계산으로 VRAM 절약

8. 저장
      └─ output_dir에 LoRA 어댑터 가중치만 저장 (adapter_model.safetensors)
      └─ 베이스 모델 가중치는 저장하지 않음 (수백 GB 절약)
```

### 메모리 구성 (A100 80 GB 기준)

| 항목 | 메모리 |
|------|--------|
| 26B 모델 가중치 (bf16) | ~52 GB |
| 활성화 + LoRA 옵티마이저 상태 | ~10–15 GB |
| **여유** | **~13–18 GB** |

| 기법 | 효과 |
|------|------|
| bf16 전체 정밀도 | 양자화 없이 수치 품질 최대화 |
| LoRA (rank=32) | 학습 파라미터 수 ~500배 감소 |
| adamw_torch_fused | A100 Tensor Core에 최적화된 fused kernel |
| gradient_checkpointing | 중간 활성화 재계산으로 VRAM 추가 절약 |
| `expandable_segments:True` | CUDA 12.8 메모리 단편화 방지 |

---

## 학습 결과 사용 (Inference)

```python
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer
import torch

base_model = AutoModelForCausalLM.from_pretrained(
    "google/gemma-4-E4B-it",
    torch_dtype=torch.bfloat16,
    device_map="auto",
)
model = PeftModel.from_pretrained(base_model, "./output")
tokenizer = AutoTokenizer.from_pretrained("./output")
```

---

## 파일 구조

```
.
├── config.yaml            # 모든 하이퍼파라미터 설정
├── train_lora.py          # 메인 학습 스크립트
├── run_train.sh           # 실행 셸 스크립트 (로컬 & Docker entrypoint 공용)
├── requirements.txt       # Python 의존성
├── .env                   # 환경 변수 (API 키 등) — git 추적 제외
├── .env.example           # .env 형식 예시 (git 추적 포함)
├── README.md              # 이 문서
└── data/
    └── finetune_dataset.jsonl  # 로컬 데이터셋 참고용 (학습은 HuggingFace Hub 사용)
```
