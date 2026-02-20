"""
fusion.py
OmniParser 결과와 Playwright AX Tree를 IoU 기반으로 병합합니다.
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


def _flatten_ax(node: dict, results: list[dict]) -> None:
    """AX Tree를 재귀적으로 평탄화"""
    if node.get("name") and node.get("role") not in ("none", "generic", "group", "region"):
        results.append({
            "role": node.get("role", ""),
            "name": node.get("name", "").strip(),
            "focusable": node.get("focusable", False),
            "disabled": node.get("disabled", False),
            "checked": node.get("checked"),
            "expanded": node.get("expanded"),
        })
    for child in node.get("children", []):
        _flatten_ax(child, results)


async def _get_ax_bboxes(page, ax_nodes: list[dict]) -> list[dict]:
    """AX 노드별 bounding_box를 Playwright에서 조회"""
    results = []
    for node in ax_nodes:
        try:
            locator = page.get_by_role(node["role"], name=node["name"], exact=True)
            bb = await locator.first.bounding_box(timeout=1000)
            if bb:
                results.append({
                    **node,
                    "bbox_px": [bb["x"], bb["y"], bb["x"] + bb["width"], bb["y"] + bb["height"]],
                })
        except Exception:
            pass
    return results


async def fuse(
    page,
    omni_elements: list[dict],
    ax_snapshot: dict,
    iou_threshold: float = 0.3,
) -> list[dict]:
    """
    OmniParser 결과와 AX Tree를 병합하여 fused_elements 반환.

    반환 형식:
    [
      {
        "id": int,
        "bbox": [x1,y1,x2,y2],          # 비율값
        "omni_content": str | None,
        "interactivity": bool,
        "ax_role": str | None,
        "ax_name": str | None,
        "ax_focusable": bool,
        "source": "both" | "omni_only",  # both → locator 우선, omni_only → bbox fallback
        "iou_score": float,
      }
    ]
    """
    vw = page.viewport_size["width"]
    vh = page.viewport_size["height"]

    # AX Tree 평탄화 + bounding_box 조회
    ax_nodes: list[dict] = []
    _flatten_ax(ax_snapshot, ax_nodes)
    ax_with_bbox = await _get_ax_bboxes(page, ax_nodes)

    fused: list[dict] = []
    for i, omni_el in enumerate(omni_elements):
        b = omni_el["bbox"]
        omni_px = [b[0] * vw, b[1] * vh, b[2] * vw, b[3] * vh]

        best_ax: dict | None = None
        best_score = 0.0
        for ax in ax_with_bbox:
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
            "ax_focusable": best_ax.get("focusable", False) if matched else False,
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
