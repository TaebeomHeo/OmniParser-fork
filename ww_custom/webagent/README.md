# WebAgent 프로토타입

**OmniParser + Playwright AX Tree** 이중 융합 기반 웹 자동화 에이전트.  
`omnitool`의 구조를 웹 브라우저에 적용한 버전입니다.

---

## 폴더 구조

```
webagent/
├── app.py          # Gradio UI (진입점)
├── loop.py         # 메인 에이전트 루프
├── fusion.py       # OmniParser + AX Tree 융합 레이어
├── executor.py     # Playwright 액션 실행 (locator 우선 / bbox fallback)
└── agent/
    └── vlm_agent.py  # GPT-4o LLM 의사결정
```

---

## 사전 준비

```bash
conda activate omni

# Playwright 설치
pip install playwright httpx openai
playwright install chromium

# OmniParser 서버 실행 (별도 터미널)
cd ../../omnitool/omniparserserver
python -m omniparserserver --device cpu --port 8000
```

---

## 실행

```bash
cd ww_custom/webagent

python app.py \
  --omniparser_url localhost:8000 \
  --openai_api_key sk-YOUR_KEY \
  --model gpt-4o \
  --start_url https://www.samsung.com/uk/tvs/all-tvs/
```

브라우저에서 `http://127.0.0.1:7862` 접속 후:

1. 시작 URL 입력
2. 태스크 자연어 입력 (예: `"TV & AV 메뉴 클릭 후 첫 제품 페이지로 이동"`)
3. OpenAI API Key 입력
4. **▶ 실행** 클릭

---

## 에이전트 루프 흐름

```
① page.goto(url)
        ↓
② 병렬 수집
   ├── page.screenshot()              → OmniParser 전송
   └── page.accessibility.snapshot() → AX Tree 파싱
        ↓
③ Fusion (fusion.py)
   OmniParser bbox ↔ AX 노드 IoU 매핑
   source: "both" | "omni_only"
        ↓
④ LLM 결정 (agent/vlm_agent.py)
   입력: SoM 이미지 + 요소 목록
   출력: {"Next Action", "Element ID"}
        ↓
⑤ 실행 (executor.py)
   "both" → locator.click() (정확)
   "omni_only" → mouse.click(cx, cy) (fallback)
        ↓
⑥ "Next Action": "None" 까지 반복
```

---

## 지원 액션

| 액션             | 설명        |
| ---------------- | ----------- |
| `left_click`     | 요소 클릭   |
| `type`           | 텍스트 입력 |
| `scroll_down/up` | 스크롤      |
| `navigate`       | URL 이동    |
| `hover`          | 마우스 호버 |
| `wait`           | 1초 대기    |
| `None`           | 완료        |

---

## 설계 문서

→ [WEBAGENT_DESIGN.md](../WEBAGENT_DESIGN.md) — 아키텍처 전체 설계
