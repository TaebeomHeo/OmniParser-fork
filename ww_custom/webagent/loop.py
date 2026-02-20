"""
loop.py
WebAgent 메인 에이전트 루프.
매 스텝마다:
  1. 스크린샷 + AX Tree 병렬 수집
  2. OmniParser API로 분석
  3. Fusion Layer 적용
  4. LLM 결정
  5. Playwright 액션 실행
"""
from __future__ import annotations
import asyncio
import base64
import httpx
from playwright.async_api import Page

from fusion import fuse, to_screen_info, draw_element_boxes, clear_element_boxes
from executor import WebExecutor
from agent.vlm_agent import VLMAgent


async def _call_omniparser(omniparser_url: str, screenshot_b64: str) -> dict:
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"http://{omniparser_url}/parse/",
            json={"base64_image": screenshot_b64},
        )
        resp.raise_for_status()
        return resp.json()


async def web_agent_loop(
    page: Page,
    task: str,
    omniparser_url: str,
    api_key: str,
    model: str = "gpt-4o",
    max_steps: int = 20,
    output_callback=None,
):
    """
    Args:
        page: Playwright Page 객체
        task: 사용자 자연어 명령
        omniparser_url: "localhost:8000"
        api_key: OpenAI API 키
        model: LLM 모델명
        max_steps: 최대 루프 횟수 (무한 루프 방지)
        output_callback: 로그 출력 콜백
    """
    log = output_callback or print
    agent = VLMAgent(model=model, api_key=api_key, output_callback=log)
    executor = WebExecutor(output_callback=log)
    history: list[dict] = []

    log(f"🚀 Task: {task}")

    for step in range(1, max_steps + 1):
        log(f"\n{'='*50}")
        log(f"Step {step}/{max_steps}")

        # ── 1. 스크린샷 수집 ─────────────────────────────────────
        screenshot_bytes = await page.screenshot(full_page=False)
        screenshot_b64 = base64.b64encode(screenshot_bytes).decode()

        # ── 2. OmniParser 분석 ─────────────────────────────────
        log("🔍 OmniParser 분석 중...")
        omni_result = await _call_omniparser(omniparser_url, screenshot_b64)
        omni_elements = omni_result.get("parsed_content_list", [])
        som_image_b64 = omni_result.get("som_image_base64", screenshot_b64)
        log(f"   감지 요소: {len(omni_elements)}개")

        # ── 3. Fusion Layer ──────────────────────────────────────────────
        log("🔗 Playwright 요소 융합 중...")
        fused_elements = await fuse(page, omni_elements, log=log, verbose=True)
        interactive = [e for e in fused_elements if e["interactivity"]]

        # 모든 인터랙티브 요소에 빨간/주황 테두리 표시
        log("🔴 요소 시각화 중...")
        await draw_element_boxes(page, fused_elements, interactive_only=True)
        log(f"   표시됨: 빨간색=이중확인(both), 주황색=OmniParser만")

        screen_info = to_screen_info(fused_elements)

        # ── 4. LLM 결정 ────────────────────────────────────────
        log("🤔 LLM 결정 중...")
        action_json = agent.decide(
            task=task,
            som_image_b64=som_image_b64,
            screen_info=screen_info,
            history=history,
        )
        log(f"   → {action_json.get('Next Action')} / Element {action_json.get('Element ID', '-')}")
        log(f"   Reasoning: {action_json.get('Reasoning', '')[:100]}...")

        # 히스토리 축적 (최근 6턴만 유지)
        history.append({"role": "assistant", "content": str(action_json)})
        if len(history) > 6:
            history = history[-6:]

        # ── 5. 실행 ───────────────────────────────────────────
        done = await executor.execute(page, action_json, fused_elements)
        if done:
            log("\n✅ 태스크 완료!")
            return

    log(f"\n⚠️ 최대 스텝({max_steps}) 도달. 루프 종료.")
