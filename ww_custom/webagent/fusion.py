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

async def _get_interactive_elements(page, viewport_only: bool = True) -> list[dict]:
    """
    Playwright 1.58+ 호환: locator 기반으로 인터랙티브 요소 + bounding_box 수집
    (page.accessibility.snapshot() 대체)

    Args:
        page: Playwright Page 객체
        viewport_only: True면 현재 뷰포트 내 요소만 반환 (OmniParser와 범위 일치)
    """
    vw = page.viewport_size["width"]
    vh = page.viewport_size["height"]
    results = []
    try:
        locators = await page.locator(INTERACTIVE_SELECTOR).all()
        for loc in locators:
            try:
                bb = await loc.bounding_box(timeout=500)
                if not bb or bb["width"] == 0 or bb["height"] == 0:
                    continue

                # 뷰포트 필터링: 요소가 화면 밖이면 스킵
                if viewport_only:
                    # 요소의 우하단이 화면 좌상단보다 왼쪽/위에 있으면 스킵
                    if bb["x"] + bb["width"] < 0 or bb["y"] + bb["height"] < 0:
                        continue
                    # 요소의 좌상단이 화면 우하단보다 오른쪽/아래에 있으면 스킵
                    if bb["x"] > vw or bb["y"] > vh:
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
    log=None,
    verbose: bool = False,
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
    _log = log or (lambda x: None)
    vw = page.viewport_size["width"]
    vh = page.viewport_size["height"]

    # ── OmniParser 요소 로깅 ──
    if verbose:
        _log(f"\n📊 OmniParser 감지 요소 ({len(omni_elements)}개):")
        for i, el in enumerate(omni_elements):
            content = el.get("content", "")[:40]
            inter = "✓" if el.get("interactivity") else "·"
            _log(f"   [{i:3d}] {inter} {content}")

    # Playwright 인터랙티브 요소 + bounding_box 수집
    interactive_els = await _get_interactive_elements(page)

    # ── Playwright 요소 로깅 ──
    if verbose:
        _log(f"\n🌐 Playwright 인터랙티브 요소 ({len(interactive_els)}개):")
        for j, ax in enumerate(interactive_els):
            name = (ax.get("name") or "")[:40]
            _log(f"   [{j:3d}] <{ax.get('tag', '?')}> [{ax.get('role')}] {name}")

    fused: list[dict] = []
    matched_count = 0
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
        if matched:
            matched_count += 1
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

    # ── Fusion 결과 요약 ──
    if verbose:
        interactive_fused = [e for e in fused if e["interactivity"]]
        both_fused = [e for e in interactive_fused if e["source"] == "both"]
        omni_only_fused = [e for e in interactive_fused if e["source"] == "omni_only"]
        _log(f"\n🔗 Fusion 결과:")
        _log(f"   OmniParser 전체: {len(omni_elements)}개")
        _log(f"   Playwright 전체: {len(interactive_els)}개")
        _log(f"   인터랙티브 요소: {len(interactive_fused)}개")
        _log(f"   ├─ 이중확인(both): {len(both_fused)}개")
        _log(f"   └─ OmniParser만: {len(omni_only_fused)}개")

        # 좌표 비교 디버깅: 처음 3개 Playwright 요소 vs OmniParser 요소
        _log(f"\n🔍 좌표 비교 (Playwright vs OmniParser):")
        for j, ax in enumerate(interactive_els[:5]):
            ax_box = ax["bbox_px"]
            _log(f"   PW[{j}] {ax.get('name','')[:20]:20s} → bbox_px: [{ax_box[0]:.0f}, {ax_box[1]:.0f}, {ax_box[2]:.0f}, {ax_box[3]:.0f}]")

        _log(f"   ---")
        for i, el in enumerate(fused[:5]):
            b = el["bbox"]
            omni_px = [b[0]*vw, b[1]*vh, b[2]*vw, b[3]*vh]
            _log(f"   OP[{i}] {el.get('omni_content','')[:20]:20s} → bbox_px: [{omni_px[0]:.0f}, {omni_px[1]:.0f}, {omni_px[2]:.0f}, {omni_px[3]:.0f}]")

        _log(f"\n📋 최종 인터랙티브 요소 목록:")
        for el in interactive_fused:
            src = "✓" if el["source"] == "both" else "~"
            role = el["ax_role"] or "icon"
            label = el["ax_name"] or el["omni_content"] or "(unknown)"
            label = label[:50]
            _log(f"   [{el['id']:3d}] {src} [{role}] {label} (IoU:{el['iou_score']:.2f})")

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


# 모든 인터랙티브 요소에 빨간 테두리 표시용 JavaScript
DRAW_ALL_BOXES_JS = """
(elements) => {
    // 기존 하이라이트 모두 제거
    document.querySelectorAll('.webagent-box').forEach(el => el.remove());

    elements.forEach((el) => {
        const color = el.source === 'both' ? '#ff0000' : '#ff8c00';
        const div = document.createElement('div');
        div.className = 'webagent-box';
        div.style.cssText = `
            position: fixed;
            left: ${el.x}px;
            top: ${el.y}px;
            width: ${el.width}px;
            height: ${el.height}px;
            border: 2px solid ${color};
            background: ${color}22;
            pointer-events: none;
            z-index: 999999;
            box-sizing: border-box;
        `;
        // ID + 라벨
        const label = document.createElement('span');
        const labelText = el.label ? `${el.id}: ${el.label}` : `${el.id}`;
        label.style.cssText = `
            position: absolute;
            top: 0;
            left: 0;
            background: ${color};
            color: white;
            font-size: 9px;
            padding: 1px 4px;
            font-family: monospace;
            white-space: nowrap;
            max-width: 150px;
            overflow: hidden;
            text-overflow: ellipsis;
        `;
        label.textContent = labelText;
        div.appendChild(label);
        document.body.appendChild(div);
    });
}
"""

CLEAR_ALL_BOXES_JS = """
() => {
    document.querySelectorAll('.webagent-box').forEach(el => el.remove());
}
"""


async def draw_element_boxes(page, fused_elements: list[dict], interactive_only: bool = True, log=None):
    """
    감지된 요소들에 빨간/주황 테두리 표시
    - both (OmniParser + AX Tree): 빨간색
    - omni_only: 주황색
    """
    _log = log or (lambda x: None)
    vw = page.viewport_size["width"]
    vh = page.viewport_size["height"]

    # 스크롤 오프셋 확인 (페이지가 스크롤된 경우 보정 필요)
    scroll_y = await page.evaluate("window.scrollY")
    _log(f"   뷰포트: {vw}x{vh}, scrollY: {scroll_y}")

    elements_data = []
    for el in fused_elements:
        if interactive_only and not el["interactivity"]:
            continue
        bbox = el["bbox"]
        # bbox는 비율값 [x1, y1, x2, y2] (0~1 범위)
        # OmniParser는 스크린샷(뷰포트) 기준 좌표를 반환
        # position:fixed는 뷰포트 기준이므로 그대로 사용
        x = bbox[0] * vw
        y = bbox[1] * vh
        w = (bbox[2] - bbox[0]) * vw
        h = (bbox[3] - bbox[1]) * vh
        elements_data.append({
            "id": el["id"],
            "x": x,
            "y": y,
            "width": w,
            "height": h,
            "source": el["source"],
            "label": (el.get("ax_name") or el.get("omni_content") or "")[:20],
        })

    _log(f"   시각화 요소: {len(elements_data)}개")
    await page.evaluate(DRAW_ALL_BOXES_JS, elements_data)


async def clear_element_boxes(page):
    """모든 요소 테두리 제거"""
    await page.evaluate(CLEAR_ALL_BOXES_JS)
