"""
executor.py
Playwright 기반 웹 액션 실행기.
source=="both" 이면 DOM locator 우선, "omni_only" 이면 bbox 좌표 클릭 fallback.
"""
from __future__ import annotations
import asyncio
from typing import Any


def _center_px(bbox: list[float], page) -> tuple[float, float]:
    vw = page.viewport_size["width"]
    vh = page.viewport_size["height"]
    return (bbox[0] + bbox[2]) / 2 * vw, (bbox[1] + bbox[3]) / 2 * vh


class WebExecutor:
    def __init__(self, output_callback=None):
        self.output_callback = output_callback or print

    async def execute(self, page, action_json: dict, fused_elements: list[dict]) -> bool:
        """
        action_json 예:
          {"Reasoning": "...", "Next Action": "left_click", "Element ID": 42}
          {"Reasoning": "...", "Next Action": "type", "Element ID": 5, "value": "hello"}
          {"Reasoning": "...", "Next Action": "navigate", "url": "https://..."}
          {"Reasoning": "...", "Next Action": "None"}

        반환값: True = 완료(루프 종료), False = 계속
        """
        action = action_json.get("Next Action", "None")

        if action == "None":
            self.output_callback("✅ 태스크 완료")
            return True

        # 요소 조회
        el: dict | None = None
        if "Element ID" in action_json:
            eid = int(action_json["Element ID"])
            matches = [e for e in fused_elements if e["id"] == eid]
            el = matches[0] if matches else None

        self.output_callback(f"▶ {action}" + (f" → Element {eid}" if el else ""))

        try:
            match action:
                case "left_click":
                    await self._click(page, el, "left")
                case "right_click":
                    await self._click(page, el, "right")
                case "double_click":
                    await self._click(page, el, "double")
                case "type":
                    value = action_json.get("value", "")
                    await self._type(page, el, value)
                case "hover":
                    cx, cy = _center_px(el["bbox"], page)
                    await page.mouse.move(cx, cy)
                case "scroll_down":
                    await page.mouse.wheel(0, 400)
                case "scroll_up":
                    await page.mouse.wheel(0, -400)
                case "navigate":
                    url = action_json.get("url", "")
                    await page.goto(url, wait_until="domcontentloaded")
                case "wait":
                    await asyncio.sleep(1)
                case _:
                    self.output_callback(f"⚠️ 알 수 없는 액션: {action}")

        except Exception as e:
            self.output_callback(f"❌ 실행 오류: {e}")

        # 액션 후 DOM 안정화 대기
        await asyncio.sleep(0.7)
        return False

    async def _click(self, page, el: dict | None, mode: str = "left"):
        if el is None:
            return
        if el["source"] == "both" and el["ax_role"] and el["ax_name"]:
            # 우선: DOM locator 사용 (정확)
            locator = page.get_by_role(el["ax_role"], name=el["ax_name"], exact=True)
            try:
                if mode == "left":
                    await locator.first.click(timeout=3000)
                elif mode == "right":
                    await locator.first.click(button="right", timeout=3000)
                elif mode == "double":
                    await locator.first.dblclick(timeout=3000)
                return
            except Exception:
                pass  # fallback으로
        # fallback: bbox 중심 좌표 클릭
        cx, cy = _center_px(el["bbox"], page)
        if mode == "left":
            await page.mouse.click(cx, cy)
        elif mode == "right":
            await page.mouse.click(cx, cy, button="right")
        elif mode == "double":
            await page.mouse.dblclick(cx, cy)

    async def _type(self, page, el: dict | None, value: str):
        if el is None:
            await page.keyboard.type(value)
            return
        if el["source"] == "both" and el["ax_role"] and el["ax_name"]:
            locator = page.get_by_role(el["ax_role"], name=el["ax_name"], exact=True)
            try:
                await locator.first.fill(value, timeout=3000)
                return
            except Exception:
                pass
        cx, cy = _center_px(el["bbox"], page)
        await page.mouse.click(cx, cy)
        await page.keyboard.type(value)
