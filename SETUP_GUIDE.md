# OmniParser 설치 및 실행 가이드 (Mac / Apple Silicon)

> **Branch**: `ww_custom`  
> **작성일**: 2026-02-20  
> **테스트 환경**: MacBook (Apple Silicon M-chip), macOS

---

## 📋 목차

1. [사전 준비](#1-사전-준비)
2. [Miniconda 설치](#2-miniconda-설치)
3. [conda 환경 생성](#3-conda-환경-생성)
4. [Python 패키지 설치](#4-python-패키지-설치)
5. [모델 가중치 다운로드](#5-모델-가중치-다운로드)
6. [Gradio 데모 실행](#6-gradio-데모-실행)
7. [코드 변경 사항 요약](#7-코드-변경-사항-요약)
8. [문제 해결 FAQ](#8-문제-해결-faq)

---

## 1. 사전 준비

Homebrew(패키지 관리자)가 설치되어 있는지 확인합니다.

```bash
brew --version
```

설치되어 있지 않으면 [https://brew.sh](https://brew.sh) 에서 설치합니다.

---

## 2. Miniconda 설치

> ❗ **주의**: `brew install --cask miniconda` 방식은 Apple Silicon에서 conda binary가 broken될 수 있습니다.  
> 아래의 **직접 installer 방식**을 사용하세요.

### 2-1. Apple Silicon (M1/M2/M3) 용 installer 다운로드 및 설치

```bash
# Apple Silicon (arm64) 버전 다운로드
curl -fsSL https://repo.anaconda.com/miniconda/Miniconda3-latest-MacOSX-arm64.sh -o /tmp/miniconda.sh

# 홈 디렉토리에 설치 (sudo 불필요)
bash /tmp/miniconda.sh -b -p ~/miniconda3
```

### 2-2. Anaconda Terms of Service 동의

처음 실행 시 아래 명령이 필요할 수 있습니다.

```bash
~/miniconda3/bin/conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main
~/miniconda3/bin/conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r
```

### 2-3. 설치 확인

```bash
~/miniconda3/bin/conda --version
# 출력 예: conda 24.x.x
```

---

## 3. conda 환경 생성

> ⚠️ **Python 3.12를 사용하세요.** Python 3.13은 일부 패키지와 호환되지 않습니다.

```bash
~/miniconda3/bin/conda create -n omni python=3.12 -y
```

환경 확인:

```bash
~/miniconda3/bin/conda env list
# omni 환경이 목록에 나타나야 합니다.
```

---

## 4. Python 패키지 설치

> ⚠️ **Mac에서 설치 제외 패키지**: `paddlepaddle`, `paddleocr`, `uiautomation`은 Mac에서 호환이 안 됩니다.  
> EasyOCR을 기본으로 사용합니다.

### 4-1. 핵심 패키지 설치

```bash
~/miniconda3/envs/omni/bin/pip install \
    torch torchvision \
    easyocr \
    "supervision==0.18.0" \
    "openai==1.3.5" \
    "transformers==4.49.0" \
    "ultralytics==8.3.70" \
    "numpy==1.26.4" \
    opencv-python \
    gradio \
    accelerate \
    timm \
    "einops==0.8.0"
```

### 4-2. transformers 버전 주의사항

`transformers 5.x`는 Florence-2 모델과 **호환되지 않습니다**.  
반드시 `transformers==4.49.0`을 사용하세요.

```bash
# 버전 확인
~/miniconda3/envs/omni/bin/pip show transformers | grep Version
# Version: 4.49.0 이어야 함
```

---

## 5. 모델 가중치 다운로드

**OmniParser V2** 모델 가중치를 HuggingFace에서 다운로드합니다.  
총 용량: 약 **1.1GB** (icon_detect ~40MB + icon_caption ~1.08GB)

```bash
cd /path/to/OmniParser-fork
mkdir -p weights

~/miniconda3/envs/omni/bin/python - <<'EOF'
from huggingface_hub import hf_hub_download

files = [
    'icon_detect/train_args.yaml',
    'icon_detect/model.pt',
    'icon_detect/model.yaml',
    'icon_caption/config.json',
    'icon_caption/generation_config.json',
    'icon_caption/model.safetensors',
]
for f in files:
    print(f'Downloading {f}...')
    hf_hub_download(
        repo_id='microsoft/OmniParser-v2.0',
        filename=f,
        local_dir='weights'
    )
    print(f'  Done.')
print('All done!')
EOF
```

다운로드 후 폴더 이름 변경 (필수):

```bash
mv weights/icon_caption weights/icon_caption_florence
```

최종 weights 폴더 구조:

```
weights/
├── icon_detect/
│   ├── model.pt
│   ├── model.yaml
│   └── train_args.yaml
└── icon_caption_florence/
    ├── config.json
    ├── generation_config.json
    └── model.safetensors
```

---

## 6. Gradio 데모 실행

```bash
cd /path/to/OmniParser-fork
~/miniconda3/envs/omni/bin/python gradio_demo.py
```

실행 후 브라우저에서 접속:

- **로컬**: http://127.0.0.1:7861
- **공개 URL** (자동 생성, 1주일 유효): 터미널 출력에서 확인

### 테스트 방법

1. 이미지 업로드 (UI 스크린샷, 앱 화면 등)
2. **"Use PaddleOCR" 체크 해제** (Mac에서 PaddleOCR 미지원)
3. **Submit** 클릭
4. 우측에 파싱된 이미지 + 요소 목록 확인

> ⏱️ **첫 실행 시** Florence-2 모델 로딩에 1~2분 소요될 수 있습니다.  
> CPU 환경이면 이미지 처리에 수 분이 걸릴 수 있습니다.

---

## 7. 코드 변경 사항 요약

이 `ww_custom` 브랜치에서 변경한 내용입니다.

### 7-1. `gradio_demo.py`

| 변경 전                         | 변경 후                                                                        | 이유                                                    |
| ------------------------------- | ------------------------------------------------------------------------------ | ------------------------------------------------------- |
| `DEVICE = torch.device('cuda')` | `DEVICE = torch.device('mps' if torch.backends.mps.is_available() else 'cpu')` | Mac은 CUDA 없음. Apple Silicon은 MPS, 나머지는 CPU 사용 |

### 7-2. `util/utils.py`

| 변경 내용                                                                    | 이유                                             |
| ---------------------------------------------------------------------------- | ------------------------------------------------ |
| `from paddleocr import PaddleOCR` → `try/except ImportError`로 조건부 import | Mac에서 paddleocr 미지원 시 crash 방지           |
| `PADDLEOCR_AVAILABLE` flag 추가                                              | EasyOCR 폴백 처리 가능                           |
| `reader = easyocr.Reader(['en'])` 위치 수정                                  | paddleocr import 분리 후 reader 초기화 누락 복구 |

---

## 8. 문제 해결 FAQ

### ❓ `ModuleNotFoundError: No module named 'paddleocr'`

Mac에서는 paddleocr가 지원되지 않습니다. Gradio UI에서 **"Use PaddleOCR" 체크를 해제**하면 EasyOCR로 자동 폴백됩니다.

---

### ❓ `AttributeError: TokenizersBackend has no attribute additional_special_tokens`

`transformers` 버전이 너무 높습니다. 다운그레이드하세요:

```bash
~/miniconda3/envs/omni/bin/pip install "transformers==4.49.0"
```

---

### ❓ conda 명령어를 매번 전체 경로로 입력해야 하나요?

shell에 conda를 초기화하면 편하게 사용할 수 있습니다:

```bash
~/miniconda3/bin/conda init zsh
# 터미널 재시작 후
conda activate omni
python gradio_demo.py
```

---

### ❓ 다음에 다시 실행하려면?

```bash
# conda 초기화가 되어 있다면
conda activate omni
cd /path/to/OmniParser-fork
python gradio_demo.py

# conda 초기화 없이
~/miniconda3/envs/omni/bin/python /path/to/OmniParser-fork/gradio_demo.py
```

---

## 📎 참고 링크

- [OmniParser 공식 GitHub](https://github.com/microsoft/OmniParser)
- [OmniParser V2 HuggingFace Model](https://huggingface.co/microsoft/OmniParser-v2.0)
- [HuggingFace Space Demo (온라인)](https://huggingface.co/spaces/microsoft/OmniParser-v2)
- [논문 (arXiv)](https://arxiv.org/abs/2408.00203)
