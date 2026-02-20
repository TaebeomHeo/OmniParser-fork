# OmniTool 구조 분석

`omnitool/`은 **Windows 11 VM을 AI 에이전트로 직접 조작**하는 완성된 컴퓨터 제어 에이전트 시스템입니다.  
OmniParser(비전 파싱) + LLM(의사결정) + Windows VM(실행)을 연결하는 3-티어 아키텍처입니다.

---

## 🏗️ 전체 아키텍처

```
┌──────────────────────────────────────────────────────────────┐
│  사용자 (브라우저)                                            │
│       ↕  Gradio UI (gradio/)  :7861                          │
├──────────┬───────────────────────────┬───────────────────────┤
│ gradio/  │  omniparserserver/        │  omnibox/             │
│ (에이전트)│  (OmniParser API 서버)    │  (Windows 11 VM)      │
│          │       :8000               │  :8006 (NoVNC 화면)   │
│          │                           │  :5000 (명령 수신)    │
└──────────┴───────────────────────────┴───────────────────────┘
```

> **분리 배포 전략**: OmniParserServer는 GPU 서버에, OmniBox+Gradio는 CPU 서버에 분리 배포 가능.

---

## 컴포넌트별 상세

### 1. `omniparserserver/` — OmniParser REST API 서버

OmniParser를 FastAPI HTTP 서버로 노출합니다.

| 엔드포인트     | 역할                                  |
| -------------- | ------------------------------------- |
| `POST /parse/` | base64 스크린샷 → bbox + content 반환 |
| `GET /probe/`  | 헬스체크                              |

```python
# 핵심 응답 구조
{
  "som_image_base64": "...",        # 번호가 그려진 어노테이션 이미지
  "parsed_content_list": [          # 감지된 UI 요소 목록
    {"type": "icon", "bbox": [...], "interactivity": True, "content": "TV & AV"},
    ...
  ],
  "latency": 1.23
}
```

**실행**:

```bash
python -m omniparserserver \
  --som_model_path ../../weights/icon_detect/model.pt \
  --caption_model_name florence2 \
  --caption_model_path ../../weights/icon_caption_florence \
  --device cuda --port 8000
```

---

### 2. `omnibox/` — Windows 11 VM (Docker)

AI가 조작할 실제 Windows 11 환경을 Docker 컨테이너로 제공합니다.

```
omnibox/
├── Dockerfile           # Windows 11 컨테이너 이미지
├── compose.yml          # Docker Compose 설정
└── vm/
    ├── win11iso/        # Windows 11 ISO 위치 (custom.iso, ~6GB)
    ├── win11def/        # VM 하드웨어 정의 (vCPU, RAM)
    ├── win11setup/      # 자동 설치 PowerShell 스크립트
    └── buildcontainer/  # 컨테이너 빌드 파일
scripts/
└── manage_vm.sh         # VM 생명주기: create / start / stop / delete
```

**VM 내부 구조**:

- `:5000` — `pyautogui` 명령 수신 HTTP 서버 (에이전트가 직접 호출)
- `:8006` — NoVNC (브라우저에서 VM 화면 시각화)

**VM 초기 설정** (최초 1회, 20~90분 소요):

```bash
cd omnitool/omnibox/scripts
./manage_vm.sh create   # ISO → VM 설치 + Docker 빌드
./manage_vm.sh start    # 이후 시작
./manage_vm.sh stop     # 중지
```

---

### 3. `gradio/` — AI 에이전트 + UI

사용자 명령 수신 → OmniParser 화면 분석 → LLM 결정 → VM 조작을 무한 루프로 실행합니다.

```
gradio/
├── app.py / app_new.py             # Gradio UI 메인 (포트 7861)
├── loop.py                         # 에이전트 메인 루프
├── agent/
│   ├── vlm_agent.py                # GPT-4o, R1, Qwen 에이전트
│   ├── vlm_agent_with_orchestrator.py  # 오케스트레이터 변형
│   └── anthropic_agent.py          # Claude Computer Use 에이전트
└── tools/
    ├── computer.py                 # VM 마우스/키보드 제어
    └── screen_capture.py           # 스크린샷 촬영
```

#### 지원 LLM

| 모델 선택                    | 실제 모델                       | API 제공사        |
| ---------------------------- | ------------------------------- | ----------------- |
| `omniparser + gpt-4o`        | gpt-4o-2024-11-20               | OpenAI            |
| `omniparser + o1`            | o1                              | OpenAI            |
| `omniparser + o3-mini`       | o3-mini                         | OpenAI            |
| `omniparser + R1`            | deepseek-r1-distill-llama-70b   | Groq              |
| `omniparser + qwen2.5vl`     | qwen2.5-vl-72b-instruct         | Alibaba DashScope |
| `claude-3-5-sonnet-20241022` | Claude Computer Use (직접 제어) | Anthropic         |

---

## 🔁 에이전트 실행 루프 (`loop.py`)

```
① 사용자: "크롬에서 amazon.com 검색해줘"
         ↓
② OmniParser API (port 8000) 호출
   → VM 스크린샷 캡처
   → Florence-2로 아이콘 분석
   → "icon 7: Chrome browser icon" 등 반환
         ↓
③ LLM에 스크린샷 + screen_info 전송
   LLM 응답(JSON):
   {"Reasoning": "...", "Next Action": "double_click", "Box ID": 7}
         ↓
④ Box ID 7의 bbox → 픽셀 중심 좌표 계산
   → VM HTTP API (port 5000) 호출
   → pyautogui.doubleClick(x, y) 실행
         ↓
⑤ "Next Action": "None" 이 나올 때까지 ②~④ 반복
```

#### LLM System Prompt 구조 (`vlm_agent.py`)

LLM에게 아래 형식의 JSON으로만 응답하도록 지시합니다:

```json
{
  "Reasoning": "현재 화면 분석 및 계획...",
  "Next Action": "left_click | right_click | double_click | type | scroll_up | scroll_down | hover | wait | None",
  "Box ID": 42,
  "value": "타이핑할 텍스트" // action이 type일 때만
}
```

#### `computer.py` — VM 명령 전송

```python
def send_to_vm(self, action: str):
    """pyautogui 명령을 VM의 :5000 HTTP 서버로 전송"""
    requests.post("http://localhost:5000/execute",
        json={"command": ["python", "-c", f"import pyautogui; {action}"]})
```

지원 액션: `key`, `type`, `mouse_move`, `left_click`, `left_click_drag`,  
`right_click`, `double_click`, `scroll_up`, `scroll_down`, `hover`, `wait`, `screenshot`

---

## 🚀 실행 방법 (3단계)

```bash
# 1. OmniParser API 서버 (GPU 서버에서)
cd omnitool/omniparserserver
python -m omniparserserver

# 2. Windows 11 VM (CPU 서버에서)
cd omnitool/omnibox/scripts
./manage_vm.sh start

# 3. Gradio UI (CPU 서버에서)
cd omnitool/gradio
conda activate omni
python app.py \
  --windows_host_url localhost:8006 \
  --omniparser_server_url localhost:8000
# → http://127.0.0.1:7861 접속
```

---

## ⚠️ 주요 제약사항

| 항목          | 내용                                                               |
| ------------- | ------------------------------------------------------------------ |
| **OS**        | OmniBox(KVM 의존)는 Windows/Linux에서만 빠르게 실행됨. Mac 미지원  |
| **디스크**    | ISO 6GB + VM 스토리지 20GB + Docker 400MB = **약 30GB 필요**       |
| **GPU**       | OmniParserServer만 GPU 필요. 나머지는 CPU로 동작                   |
| **설치 시간** | VM 최초 설정 20~90분 소요                                          |
| **VM 재사용** | `win11storage/` 폴더에 VM 상태 저장 → 이후 `start/stop`으로 재사용 |

---

## 참고

- [OmniTool 공식 README](../omnitool/readme.md)
- [omniparserserver.py](../omnitool/omniparserserver/omniparserserver.py)
- [vlm_agent.py](../omnitool/gradio/agent/vlm_agent.py)
- [computer.py](../omnitool/gradio/tools/computer.py)
