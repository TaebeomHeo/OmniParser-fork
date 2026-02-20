"""
fusion.py
OmniParser 결과와 Playwright 인터랙티브 요소를 IoU 기반으로 병합합니다.
Playwright 1.58+ 호환 (page.accessibility 제거, locator 기반으로 대체)
"""
from __future__ import annotations
import asyncio
from typing import Any


def _iou(a: list[float], b: list[float]) -> float:
    """두 [x1,y1,x2,y2] 픽셀 박스의 IoU 계산"""
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    if inter == 0:
        return 0.0
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    return inter / (area_a + area_b - inter)


# 인터랙티브 요소를 찾는 CSS 선택자
INTERACTIVE_SELECTOR = "a, button, input, select, textarea, [role='button'], [role='link'], [role='menuitem'], [role='tab'], [tabindex]"

async def _get_interactive_elements(page) -> list[dict]:
    """
    Playwright 1.58+ 호환: locator 기반으로 인터랙티브 요소 + bounding_box 수집
    (page.accessibility.snapshot() 대체)
    """
    results = []
    try:
        locators = await page.locator(INTERACTIVE_SELECTOR).all()
        for loc in locators:
            try:
                bb = await loc.bounding_box(timeout=500)
                if not bb or bb["width"] == 0 or bb["height"] == 0:
                    continue
                role = await loc.get_attribute("role") or ""
                aria_label = await loc.get_attribute("aria-label") or ""
                text = (await loc.inner_text()).strip()[:80] if not aria_label else ""
                name = aria_label or text or ""
                tag = await loc.evaluate("el => el.tagName.toLowerCase()")
                # role 추론: HTML 태그 기반
                if not role:
                    role = {"a": "link", "button": "button", "input": "textbox",
                            "select": "combobox", "textarea": "textbox"}.get(tag, "button")
                results.append({
                    "role": role,
                    "name": name,
                    "tag": tag,
                    "bbox_px": [bb["x"], bb["y"], bb["x"] + bb["width"], bb["y"] + bb["height"]],
                })
            except Exception:
                continue
    except Exception:
        pass
    return results


async def fuse(
    page,
    omni_elements: list[dict],
    iou_threshold: float = 0.3,
) -> list[dict]:
    """
    OmniParser 결과와 Playwright 인터랙티브 요소 bounding_box를 IoU 병합.

    반환 형식:
    [
      {
        "id": int,
        "bbox": [x1,y1,x2,y2],          # 비율값
        "omni_content": str | None,
        "interactivity": bool,
        "ax_role": str | None,
        "ax_name": str | None,
        "source": "both" | "omni_only",
        "iou_score": float,
      }
    ]
    """
    vw = page.viewport_size["width"]
    vh = page.viewport_size["height"]

    # Playwright 인터랙티브 요소 + bounding_box 수집
    interactive_els = await _get_interactive_elements(page)

    fused: list[dict] = []
    for i, omni_el in enumerate(omni_elements):
        b = omni_el["bbox"]
        omni_px = [b[0] * vw, b[1] * vh, b[2] * vw, b[3] * vh]

        best_ax: dict | None = None
        best_score = 0.0
        for ax in interactive_els:
            score = _iou(omni_px, ax["bbox_px"])
            if score > best_score:
                best_score, best_ax = score, ax

        matched = best_score >= iou_threshold
        fused.append({
            "id": i,
            "bbox": omni_el["bbox"],
            "omni_content": omni_el.get("content"),
            "interactivity": omni_el.get("interactivity", False),
            "ax_role": best_ax["role"] if matched else None,
            "ax_name": best_ax["name"] if matched else None,
            "ax_tag": best_ax.get("tag") if matched else None,
            "source": "both" if matched else "omni_only",
            "iou_score": round(best_score, 3),
        })

    return fused


def to_screen_info(fused_elements: list[dict]) -> str:
    """LLM system prompt용 요소 목록 텍스트 생성"""
    lines = []
    for el in fused_elements:
        if not el["interactivity"]:
            continue
        label = el["ax_name"] or el["omni_content"] or "(unknown)"
        role = f"[{el['ax_role']}]" if el["ax_role"] else "[icon]"
        src = "✓" if el["source"] == "both" else "~"
        lines.append(f"  Element {el['id']:3d} {src} {role} {label}")
    return "\n".join(lines)
