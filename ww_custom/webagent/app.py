"""
app.py
WebAgent Gradio UI.

실행:
  python app.py --omniparser_url localhost:8000 --openai_api_key sk-...
"""
from __future__ import annotations
import argparse
import asyncio
import threading
import gradio as gr
from playwright.async_api import async_playwright
from loop import web_agent_loop


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--omniparser_url", default="localhost:8000")
    p.add_argument("--openai_api_key", default="")
    p.add_argument("--model", default="gpt-4o")
    p.add_argument("--start_url", default="https://www.google.com")
    p.add_argument("--port", type=int, default=7862)
    return p.parse_args()


args = parse_args()

# ── Gradio UI ──────────────────────────────────────────────────────────
def run_agent(task: str, start_url: str, api_key: str, max_steps: int):
    """동기 래퍼: Gradio 콜백에서 asyncio 루프 실행"""
    logs: list[str] = []

    def log_cb(msg: str):
        logs.append(msg)
        # generator yield는 Gradio streaming에서 처리
        print(msg)

    async def _run():
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=False)
            page = await browser.new_page(viewport={"width": 1280, "height": 800})
            await page.goto(start_url, wait_until="domcontentloaded")
            await web_agent_loop(
                page=page,
                task=task,
                omniparser_url=args.omniparser_url,
                api_key=api_key or args.openai_api_key,
                model=args.model,
                max_steps=int(max_steps),
                output_callback=log_cb,
            )
            await browser.close()

    asyncio.run(_run())
    return "\n".join(logs)


with gr.Blocks(title="WebAgent") as demo:
    gr.Markdown("# 🌐 WebAgent\nOmniParser + Playwright AX Tree 기반 웹 자동화 에이전트")

    with gr.Row():
        with gr.Column():
            start_url_input = gr.Textbox(
                label="시작 URL", value=args.start_url, placeholder="https://..."
            )
            task_input = gr.Textbox(
                label="태스크 (자연어)", lines=3,
                placeholder="예) TV & AV 메뉴를 클릭하고 첫 번째 제품 페이지로 이동해줘"
            )
            api_key_input = gr.Textbox(
                label="OpenAI API Key", type="password",
                value=args.openai_api_key, placeholder="sk-..."
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
        inputs=[task_input, start_url_input, api_key_input, max_steps_input],
        outputs=[log_output],
    )

if __name__ == "__main__":
    demo.launch(server_port=args.port, server_name="127.0.0.1")
