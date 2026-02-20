# WebAgent 설계 문서

## OmniParser + Playwright AX Tree 기반 웹 자동화 에이전트

OmniTool(Windows VM 제어)과 동일한 아키텍처를 웹 브라우저에 적용합니다.  
**OmniParser(시각 파싱) + Playwright AX Tree(DOM 파싱)** 를 이중으로 사용해 정확도를 높입니다.

---

## 🏗️ 전체 아키텍처

```
┌──────────────────────────────────────────────────────────────────┐
│  사용자 명령: "삼성닷컴에서 TV & AV 페이지로 이동해줘"            │
├──────────────┬───────────────────────────┬───────────────────────┤
│  webagent/   │  omniparserserver/        │  playwright browser   │
│  UI(Gradio)  │  (기존 그대로 재사용)     │  (OmniBox 대체)       │
│  + loop.py   │  :8000                    │  headless / headed    │
└──────────────┴───────────────────────────┴───────────────────────┘
```

---

## 핵심: OmniParser + AX Tree 이중 융합

```
           스크린샷 (page.screenshot)
                    ↓
       ┌────────────┴────────────┐  병렬 실행
       ↓                         ↓
  OmniParser 분석          AX Tree 분석
  (omniparserserver)       (page.accessibility.snapshot)
  → bbox + content         → role + name + focusable
  → interactivity flag     → DOM 위치 정보
       ↓                         ↓
       └────────────┬────────────┘
                    ↓
             Fusion Layer
          (IoU 매핑으로 병합)
                    ↓
            통합 요소 목록
   [{ id, bbox, omni_content, ax_role, ax_name, source }]
                    ↓
                  LLM
          → {"Next Action", "Element ID"}
                    ↓
               Executor
   source=="both" → locator.click()  (견고)
   source=="omni_only" → mouse.click(cx, cy)  (fallback)
```

---

## 컴포넌트 구성 비교

|                 | OmniTool                      | WebAgent                               |
| --------------- | ----------------------------- | -------------------------------------- |
| **실행 환경**   | Windows 11 VM (Docker, KVM)   | Playwright Browser                     |
| **스크린샷**    | NoVNC + pyautogui             | `page.screenshot()`                    |
| **요소 인식**   | OmniParser 단독               | OmniParser + AX Tree **이중**          |
| **클릭 실행**   | `pyautogui.click()` → VM HTTP | `locator.click()` 또는 `mouse.click()` |
| **정확도**      | 시각 기반                     | 시각 + DOM 이중 확인                   |
| **OS 의존성**   | Windows/Linux (KVM 필요)      | 크로스플랫폼 (Mac 포함)                |
| **설치 복잡도** | ISO 6GB + 20GB 스토리지, 90분 | `pip install playwright`               |

---

## AX Tree 병렬 사용의 장점

| 장점                | 설명                                                    |
| ------------------- | ------------------------------------------------------- |
| **OCR 오탈자 보정** | `"comfuk"` → AX Tree의 정확한 `name`으로 수정           |
| **클릭 신뢰도**     | `locator.click()`은 DOM 직접 접근, 픽셀 오차 없음       |
| **동적 UI 대응**    | SPA/React 앱처럼 좌표가 바뀌어도 `role+name`으로 재탐색 |
| **invisible 요소**  | 작아서 OmniParser가 놓친 요소도 AX Tree로 캐치          |
| **상태 확인**       | `disabled`, `checked`, `expanded` 등 DOM 상태 활용      |

---

## 에이전트 루프 흐름 (loop.py)

```
① page.goto(url)
        ↓
② 병렬 수집
   ├── page.screenshot()           → OmniParser API로 전송
   └── page.accessibility.snapshot()  → AX Tree 파싱
        ↓
③ Fusion Layer
   OmniParser bbox ↔ AX Tree 노드 IoU 매핑
   → 통합 fused_elements 생성
        ↓
④ LLM 결정
   입력: 스크린샷(SoM 이미지) + fused_elements 텍스트
   출력: {"Reasoning": "...", "Next Action": "left_click", "Element ID": 42}
        ↓
⑤ Executor 실행
   Element ID → fused_elements 조회
   source == "both"      → locator.click()  (우선)
   source == "omni_only" → mouse.click(cx, cy)  (fallback)
        ↓
⑥ "Next Action": "None" 까지 ②~⑤ 반복
```

---

## LLM System Prompt 구조

LLM에게 아래 형식의 JSON으로만 응답하도록 지시:

```json
{
  "Reasoning": "현재 화면에서 TV & AV 링크(Element 42)가 nav bar에 보임. 클릭하면 해당 페이지로 이동.",
  "Next Action": "left_click",
  "Element ID": 42
}
```

지원 액션:
| 액션 | 설명 |
|---|---|
| `left_click` | 요소 클릭 |
| `type` | 텍스트 입력 (+ `value` 필드) |
| `scroll_down` / `scroll_up` | 스크롤 |
| `navigate` | URL 직접 이동 (+ `url` 필드) |
| `hover` | 마우스 호버 |
| `wait` | 1초 대기 |
| `None` | 태스크 완료 |

---

## Fusion 전략 상세

```
OmniParser 요소             AX Tree 노드
bbox: [0.29, 0.05, 0.32, 0.07]    role: "link", name: "TV & AV"
content: "TV &AV"                  대응 bounding_box: {x:440, y:43...}
interactivity: True

           IoU 계산
           (픽셀 변환 후 겹침 비율)
                ↓
           IoU > 0.3 이면 "both"
           IoU ≤ 0.3 이면 "omni_only"

최종 fused 요소:
{
  "id": 42,
  "bbox": [0.29, 0.05, 0.32, 0.07],
  "omni_content": "TV &AV",            ← OmniParser
  "ax_role": "link",                   ← AX Tree
  "ax_name": "TV & AV",               ← AX Tree (정확한 텍스트)
  "interactivity": True,
  "source": "both",                    ← 이중 감지 → locator 우선 사용
  "iou_score": 0.87
}
```

---

## 폴더 구조

```
ww_custom/webagent/
├── README.md              # 사용법 및 실행 방법
├── loop.py                # 메인 에이전트 루프
├── fusion.py              # OmniParser + AX Tree 융합 레이어
├── executor.py            # Playwright 액션 실행
├── agent/
│   └── vlm_agent.py       # LLM 의사결정 (omnitool 코드 기반)
├── tools/
│   └── browser.py         # Playwright 래퍼 (스크린샷, 네비게이션)
└── app.py                 # Gradio UI
```

---

## 실행 방법

```bash
# 1. OmniParser 서버 실행 (기존과 동일)
cd omnitool/omniparserserver
python -m omniparserserver --device cpu --port 8000

# 2. Playwright 설치
conda activate omni
pip install playwright
playwright install chromium

# 3. WebAgent 실행
cd ww_custom/webagent
python app.py --omniparser_url localhost:8000 --start_url https://www.samsung.com/uk/tvs/all-tvs/
```

---

## 참고

- [OMNITOOL_ANALYSIS.md](../OMNITOOL_ANALYSIS.md) — 원본 OmniTool 구조 분석
- [PLAYWRIGHT_INTEGRATION.md](../PLAYWRIGHT_INTEGRATION.md) — Playwright 연동 방법
- [omniparserserver.py](../../omnitool/omniparserserver/omniparserserver.py)
