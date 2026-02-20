# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

OmniParser is a screen parsing tool that converts GUI screenshots into structured UI elements using YOLO (icon detection) + Florence-2 (icon captioning) + OCR. This fork (`ww_custom` branch) adds:
- **OmniTool**: Windows 11 VM control agent via Docker
- **WebAgent**: Playwright-based web automation with OmniParser + AX Tree fusion

## Common Commands

### Environment Setup
```bash
conda create -n omni python=3.12
conda activate omni
pip install -r requirements.txt

# Download model weights (~1.1GB)
for f in icon_detect/{train_args.yaml,model.pt,model.yaml} icon_caption/{config.json,generation_config.json,model.safetensors}; do
  huggingface-cli download microsoft/OmniParser-v2.0 "$f" --local-dir weights
done
mv weights/icon_caption weights/icon_caption_florence
```

### Running the Demo
```bash
python gradio_demo.py  # Opens at http://127.0.0.1:7861
```

### Running OmniParser API Server
```bash
cd omnitool/omniparserserver
python -m omniparserserver --device cpu --port 8000
# API endpoints: POST /parse/ (base64 image) and GET /probe/ (health check)
```

### Running WebAgent
```bash
# Install Playwright
pip install playwright
playwright install chromium

# Start WebAgent UI
cd ww_custom/webagent
python app.py --omniparser_url localhost:8000
```

### Testing
```bash
pytest
```

## Architecture

### Three-Tier System
```
UI Layer (Gradio)
    ↓
Agent Layer (LLM decision-making: GPT-4o, Claude, DeepSeek, Qwen)
    ↓
Perception Layer (OmniParser: YOLO + Florence-2 + OCR)
```

### Core Components

**Perception (`util/`)**:
- `omniparser.py`: Main `Omniparser` class - loads models and runs `parse(image_base64)`
- `utils.py`: Model loading (`get_yolo_model`, `get_caption_model_processor`), OCR (`check_ocr_box`), pipeline (`get_som_labeled_img`)

**OmniParser Server (`omnitool/omniparserserver/`)**:
- FastAPI wrapper exposing `/parse/` endpoint for remote GPU inference

**OmniTool Agent (`omnitool/gradio/`)**:
- `app.py`: Gradio UI entry point
- `loop.py`: Main agent loop (screenshot → OmniParser → LLM → action → repeat)
- `agent/vlm_agent.py`: Vision-Language Model integration (OpenAI, DeepSeek, Qwen)
- `agent/anthropic_agent.py`: Claude with native tool use
- `tools/computer.py`: Mouse/keyboard control via HTTP to Windows VM

**WebAgent (`ww_custom/webagent/`)**:
- `fusion.py`: IoU-based mapping between OmniParser bounding boxes and Playwright AX Tree nodes
- `executor.py`: Playwright action execution (prefers `locator.click()` for DOM-matched elements, falls back to `mouse.click(cx, cy)`)

### Model Weights Structure
```
weights/
├── icon_detect/          # YOLOv8 for UI element detection
│   └── model.pt
└── icon_caption_florence/  # Florence-2 for icon description
    └── model.safetensors
```

## Platform Notes

### Mac/Apple Silicon
- Use `mps` device instead of `cuda`
- PaddleOCR not supported - uncheck "Use PaddleOCR" in Gradio UI (falls back to EasyOCR)
- Requires `transformers==4.49.0` (v5.x incompatible with Florence-2)

### Dependencies to Exclude on Mac
`paddlepaddle`, `paddleocr`, `uiautomation` are Windows-only

## API Keys

Create `.env` file with:
```
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=...
```

Load via `python-dotenv` in agent code.
