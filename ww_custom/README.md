# ww_custom — OmniParser 커스텀 문서 모음

이 폴더는 **WiseWires** 내부용 OmniParser 분석 및 활용 가이드를 담고 있습니다.

## 📂 문서 목록

| 파일                                                     | 내용                                                              |
| -------------------------------------------------------- | ----------------------------------------------------------------- |
| [SETUP_GUIDE.md](./SETUP_GUIDE.md)                       | Mac Apple Silicon 환경 설치 및 Gradio 데모 실행 가이드            |
| [PLAYWRIGHT_INTEGRATION.md](./PLAYWRIGHT_INTEGRATION.md) | OmniParser 분석 결과를 Playwright와 연결하는 방법                 |
| [OMNITOOL_ANALYSIS.md](./OMNITOOL_ANALYSIS.md)           | omnitool/ 구조 상세 분석 (3개 컴포넌트, 에이전트 루프, 실행 방법) |
| [WEBAGENT_DESIGN.md](./WEBAGENT_DESIGN.md)               | OmniParser + Playwright AX Tree 이중 융합 WebAgent 아키텍처 설계  |
| [webagent/](./webagent/)                                 | WebAgent 프로토타입 코드 (loop, fusion, executor, vlm_agent, app) |

## 🔄 브랜치 변경 사항 요약

이 `ww_custom` 브랜치는 원본 OmniParser 레포에서 다음을 수정했습니다.

| 파일             | 변경 내용                                      |
| ---------------- | ---------------------------------------------- |
| `gradio_demo.py` | `DEVICE = cuda` → MPS/CPU 자동 선택 (Mac 호환) |
| `util/utils.py`  | `paddleocr` import → `try/except` 조건부 처리  |
