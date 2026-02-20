"""
agent/vlm_agent.py
OmniParser fused_elements + 스크린샷을 LLM에 전달해 다음 액션을 결정합니다.
omnitool/gradio/agent/vlm_agent.py 를 웹 에이전트용으로 단순화한 버전.
"""
from __future__ import annotations
import json
import re
from openai import OpenAI


def _extract_json(text: str) -> dict:
    pattern = r"```json(.*?)(```|$)"
    match = re.search(pattern, text, re.DOTALL)
    raw = match.group(1).strip() if match else text
    return json.loads(raw)


SYSTEM_PROMPT = """\
You are a web browser automation agent.
You control a real browser via Playwright.
You are given:
1. A screenshot of the current web page (annotated with element numbers by OmniParser).
2. A list of detected interactive elements with their IDs, roles, and labels.

Your available actions:
- left_click: click an element
- right_click: right-click an element
- double_click: double-click an element
- type: type text into an element (requires "value" field)
- hover: hover over an element
- scroll_down / scroll_up: scroll the page
- navigate: go to a URL (requires "url" field)
- wait: wait 1 second
- None: task is complete

Rules:
1. Output ONLY valid JSON in the format below.
2. One action at a time.
3. Use "None" when the task is fully completed.
4. Prefer elements with source "✓" (both OmniParser + AX Tree confirmed) for clicks.
5. If a login/captcha page appears, output "None".

Output format:
```json
{
  "Reasoning": "describe current screen and your plan step by step",
  "Next Action": "action_type",
  "Element ID": 42,
  "value": "text to type"
}
```
(omit "Element ID" for scroll/navigate/wait; omit "value" unless action is "type")
"""


class VLMAgent:
    def __init__(self, api_key: str, model: str = "gpt-4o", output_callback=None):
        self.client = OpenAI(api_key=api_key)
        self.model = model
        self.output_callback = output_callback or print
        self.step = 0

    def decide(
        self,
        task: str,
        som_image_b64: str,
        screen_info: str,
        history: list[dict],
    ) -> dict:
        self.step += 1
        self.output_callback(f"── Step {self.step} ──")

        user_content = [
            {
                "type": "text",
                "text": (
                    f"Task: {task}\n\n"
                    f"Interactive elements on screen:\n{screen_info}\n\n"
                    "Screenshot (elements numbered by OmniParser):"
                ),
            },
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{som_image_b64}", "detail": "high"},
            },
        ]

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            *history,
            {"role": "user", "content": user_content},
        ]

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=1024,
            temperature=0,
        )
        raw = response.choices[0].message.content
        self.output_callback(f"LLM: {raw[:200]}...")

        try:
            return _extract_json(raw)
        except Exception:
            return {"Reasoning": raw, "Next Action": "None"}
