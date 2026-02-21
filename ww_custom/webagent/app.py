"""
app.py
WebAgent Gradio UI.

실행:
  python app.py
  (API 키는 .env 파일의 OPENAI_API_KEY에서 자동 로드)
"""
from __future__ import annotations
import argparse
import asyncio
import os
from pathlib import Path
import gradio as gr
from dotenv import load_dotenv, find_dotenv
from playwright.async_api import async_playwright, BrowserContext, Playwright
from loop import web_agent_loop

# .env 로드: 현재 디렉토리부터 상위로 탐색 (레포 루트 .env도 인식)
load_dotenv(find_dotenv(usecwd=True))

# 브라우저 데이터 저장 경로 (cache, cookies, localStorage 등)
BROWSER_DATA_DIR = Path(__file__).parent / ".browser_data"

# 전역 브라우저 인스턴스 (세션 간 재사용)
_playwright: Playwright | None = None
_browser_context: BrowserContext | None = None


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--omniparser_url", default=os.getenv("OMNIPARSER_URL", "localhost:8000"))
    p.add_argument("--model", default=os.getenv("OPENAI_MODEL", "gpt-4o"))
    p.add_argument("--start_url", default="https://www.google.com")
    p.add_argument("--port", type=int, default=7862)
    return p.parse_args()


args = parse_args()


async def get_or_create_browser():
    """브라우저 컨텍스트 반환 (없으면 생성, 있으면 재사용)"""
    global _playwright, _browser_context

    # 기존 컨텍스트가 유효한지 확인
    if _browser_context is not None:
        try:
            # 페이지 접근으로 컨텍스트 유효성 확인
            _ = _browser_context.pages
            return _browser_context
        except Exception:
            # 컨텍스트가 닫혔음 - 새로 생성 필요
            _browser_context = None

    # Playwright 시작
    if _playwright is None:
        _playwright = await async_playwright().start()

    # 새 브라우저 컨텍스트 생성
    _browser_context = await _playwright.chromium.launch_persistent_context(
        user_data_dir=str(BROWSER_DATA_DIR),
        headless=False,
        viewport={"width": 1280, "height": 800},
        locale="ko-KR",
    )
    return _browser_context


# ── Gradio UI ──────────────────────────────────────────────────────────
def run_agent(task: str, start_url: str, max_steps: int):
    """동기 래퍼: Gradio 콜백에서 asyncio 루프 실행 (브라우저 재사용)"""
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        return "❌ OPENAI_API_KEY가 .env 파일에 설정되지 않았습니다."
    logs: list[str] = []

    def log_cb(msg: str):
        logs.append(msg)
        print(msg)

    async def _run():
        # 브라우저 컨텍스트 가져오기 (기존 것 재사용 또는 새로 생성)
        context = await get_or_create_browser()

        # 새 페이지에서 URL 열기 (기존 탭은 유지)
        page = await context.new_page()
        await page.goto(start_url, wait_until="domcontentloaded")

        await web_agent_loop(
            page=page,
            task=task,
            omniparser_url=args.omniparser_url,
            api_key=api_key,
            model=args.model,
            max_steps=int(max_steps),
            output_callback=log_cb,
        )
        log_cb("\n🔍 브라우저가 열려있습니다. 결과를 확인하세요. (다음 실행 시 재사용됨)")

    # 이벤트 루프 재사용 (이미 실행 중이면 기존 루프 사용)
    try:
        loop = asyncio.get_running_loop()
        # 이미 루프가 실행 중이면 새 태스크로 실행
        future = asyncio.ensure_future(_run())
        loop.run_until_complete(future)
    except RuntimeError:
        # 루프가 없으면 새로 실행
        asyncio.run(_run())

    return "\n".join(logs)


with gr.Blocks(title="WebAgent") as demo:
    gr.Markdown(
        "# 🌐 WebAgent\n"
        "OmniParser + Playwright AX Tree 기반 웹 자동화 에이전트\n\n"
        f"> 모델: `{args.model}` | OmniParser: `{args.omniparser_url}`  "
        "| API Key: `.env` 파일에서 자동 로드"
    )

    with gr.Row():
        with gr.Column():
            start_url_input = gr.Textbox(
                label="시작 URL", value=args.start_url, placeholder="https://..."
            )
            task_input = gr.Textbox(
                label="태스크 (자연어)", lines=3,
                placeholder="예) TV & AV 메뉴를 클릭하고 첫 번째 제품 페이지로 이동해줘"
            )
            max_steps_input = gr.Slider(
                label="최대 스텝", minimum=1, maximum=50, step=1, value=15
            )
            run_btn = gr.Button("▶ 실행", variant="primary")

        with gr.Column():
            log_output = gr.Textbox(
                label="실행 로그", lines=30, placeholder="로그가 여기 출력됩니다..."
            )

    run_btn.click(
        fn=run_agent,
        inputs=[task_input, start_url_input, max_steps_input],
        outputs=[log_output],
    )

if __name__ == "__main__":
    demo.launch(server_port=args.port, server_name="127.0.0.1")
