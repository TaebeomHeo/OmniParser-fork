# OmniParser + Playwright 연동 가이드

OmniParser가 스크린샷에서 추출한 **bbox 좌표 + content 레이블**을 Playwright의 **마우스 클릭 / Locator / Accessibility Tree**와 연결하는 방법을 설명합니다.

---

## 📌 개념 구조

```
Playwright                           OmniParser
─────────────────────────────────────────────────────
page.screenshot()  ──────────────→  이미지 분석
                                      └─ bbox [x1,y1,x2,y2] (비율값)
                                      └─ content (레이블)
                                      └─ interactivity (bool)

page.accessibility.snapshot()
 └─ { role, name, children... }
     └─ bounding_box() via locator  ←──── 좌표로 매핑
```

---

## 방법 1 — bbox → `page.mouse.click()` (가장 단순)

OmniParser의 bbox(비율값)를 픽셀 좌표로 변환해 직접 클릭합니다. Accessibility Tree 없이도 동작합니다.

```python
import asyncio
from playwright.async_api import async_playwright

async def click_omniparser_element(page, bbox):
    """OmniParser bbox(비율값)를 Playwright 클릭 좌표로 변환"""
    vw = page.viewport_size['width']
    vh = page.viewport_size['height']
    x1, y1, x2, y2 = bbox
    center_x = (x1 + x2) / 2 * vw
    center_y = (y1 + y2) / 2 * vh
    await page.mouse.click(center_x, center_y)

# 예시: Samsung TV 페이지 "TV & AV" 메뉴 클릭
# icon 42: bbox = [0.294, 0.053, 0.325, 0.073]
async with async_playwright() as p:
    browser = await p.chromium.launch()
    page = await browser.new_page(viewport={"width": 1512, "height": 812})
    await page.goto("https://www.samsung.com/uk/tvs/all-tvs/")

    screenshot = await page.screenshot()
    # ... omniparser.parse(screenshot) 실행 후 bbox 획득 ...

    await click_omniparser_element(page, [0.294, 0.053, 0.325, 0.073])
    await browser.close()
```

---

## 방법 2 — content → Accessibility Tree `name` 매핑 (텍스트 요소에 견고)

OmniParser `content` 레이블로 Accessibility Tree에서 같은 이름의 노드를 찾습니다.

```python
async def find_ax_node_by_content(page, omni_content: str):
    """OmniParser content로 Accessibility Tree 노드 찾기"""
    snapshot = await page.accessibility.snapshot()

    def search(node, target):
        node_name = node.get('name', '').strip().lower()
        if target.strip().lower() in node_name:
            return node
        for child in node.get('children', []):
            result = search(child, target)
            if result:
                return result
        return None

    return search(snapshot, omni_content)

# 예시
node = await find_ax_node_by_content(page, "TV &AV")
# → { 'role': 'link', 'name': 'TV & AV', 'focusable': True }

# 찾은 노드로 실제 클릭
if node:
    locator = page.get_by_role(node['role'], name=node['name'])
    await locator.click()
```

---

## 방법 3 — bbox ↔ `locator.bounding_box()` IoU 매핑 (가장 정확)

Playwright의 모든 인터랙티브 요소 bounding_box와 OmniParser bbox의 **IoU(교차 비율)** 를 계산해 가장 높은 것을 매칭합니다.

```python
async def match_omniparser_to_locator(page, omni_bbox):
    """OmniParser bbox와 IoU가 가장 높은 Playwright locator 반환"""
    vw = page.viewport_size['width']
    vh = page.viewport_size['height']
    ox1, oy1, ox2, oy2 = (
        omni_bbox[0]*vw, omni_bbox[1]*vh,
        omni_bbox[2]*vw, omni_bbox[3]*vh
    )

    def iou(bb):
        ex1, ey1 = bb['x'], bb['y']
        ex2, ey2 = ex1 + bb['width'], ey1 + bb['height']
        ix1, iy1 = max(ox1, ex1), max(oy1, ey1)
        ix2, iy2 = min(ox2, ex2), min(oy2, ey2)
        inter = max(0, ix2-ix1) * max(0, iy2-iy1)
        a1 = (ox2-ox1) * (oy2-oy1)
        a2 = bb['width'] * bb['height']
        union = a1 + a2 - inter
        return inter / union if union > 0 else 0

    elements = await page.locator('a, button, [role="button"], input, select').all()
    best_iou, best_el = 0, None
    for el in elements:
        bb = await el.bounding_box()
        if bb:
            score = iou(bb)
            if score > best_iou:
                best_iou, best_el = score, el

    return best_el, best_iou

# 예시
el, score = await match_omniparser_to_locator(page, [0.294, 0.053, 0.325, 0.073])
if el and score > 0.5:
    await el.click()
```

---

## 전체 파이프라인 예시

```python
import base64, io
from PIL import Image
from playwright.async_api import async_playwright
from util.omniparser import Omniparser

config = {
    'som_model_path': 'weights/icon_detect/model.pt',
    'caption_model_name': 'florence2',
    'caption_model_path': 'weights/icon_caption_florence',
    'BOX_TRESHOLD': 0.05,
}
parser = Omniparser(config)

async def run_agent(url: str, task: str):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page(viewport={"width": 1512, "height": 812})
        await page.goto(url)

        # 1. 스크린샷 촬영
        screenshot_bytes = await page.screenshot()
        image_b64 = base64.b64encode(screenshot_bytes).decode()

        # 2. OmniParser 분석
        labeled_img, parsed_elements = parser.parse(image_b64)
        # parsed_elements: [{'type', 'bbox', 'interactivity', 'content'}, ...]

        # 3. 인터랙티브 요소만 필터
        interactive = [e for e in parsed_elements if e['interactivity']]
        print(f"감지된 클릭 가능 요소: {len(interactive)}개")

        # 4. LLM 또는 규칙으로 target 선택
        # (예: content에 "TV" 포함하는 첫 번째 요소 클릭)
        target = next((e for e in interactive if 'TV' in (e['content'] or '')), None)

        # 5. 방법 선택하여 클릭
        if target:
            # 방법 1: 단순 클릭
            await click_omniparser_element(page, target['bbox'])
            # 또는 방법 3: IoU locator 매핑
            # el, score = await match_omniparser_to_locator(page, target['bbox'])
            # if el: await el.click()

        await browser.close()

asyncio.run(run_agent("https://www.samsung.com/uk/tvs/all-tvs/", "TV & AV 클릭"))
```

---

## 방법별 비교

|                  | 방법 1 (mouse.click)   | 방법 2 (ax-tree name) | 방법 3 (IoU locator) |
| ---------------- | ---------------------- | --------------------- | -------------------- |
| **구현 난이도**  | ⭐ 쉬움                | ⭐⭐ 보통             | ⭐⭐⭐ 복잡          |
| **정확도**       | 🔶 중간                | ✅ 텍스트 요소에 높음 | ✅ 모든 요소에 높음  |
| **동적 UI 대응** | ❌ 취약                | 🔶 부분적             | ✅ 강함              |
| **추천 상황**    | 프로토타입/빠른 테스트 | 텍스트 링크·버튼 위주 | 프로덕션 에이전트    |

---

## 실전 팁

- **OCR 오탈자 처리**: OmniParser OCR이 `"comfuk"`, `"IIWWw"` 같은 오탈자를 낼 수 있습니다. fuzzy matching(`difflib.SequenceMatcher`)으로 보완하세요.
- **브라우저 툴바 노이즈 제거**: bbox의 `y1 < 0.05`인 요소는 브라우저 UI 영역일 가능성이 높습니다. 필터링 권장.
- **viewport 일치**: OmniParser에 넣은 스크린샷과 Playwright viewport 크기가 **반드시 동일**해야 좌표가 정확합니다.

```python
# 스크린샷 해상도와 viewport 일치 확인
screenshot = await page.screenshot(full_page=False)  # full_page=False 권장
img = Image.open(io.BytesIO(screenshot))
assert img.size == (page.viewport_size['width'], page.viewport_size['height'])
```

---

## 참고

- [OmniParser GitHub](https://github.com/microsoft/OmniParser)
- [Playwright Python Docs](https://playwright.dev/python/docs/api/class-page)
- [Playwright Accessibility](https://playwright.dev/python/docs/api/class-accessibility)
