#!/usr/bin/env python3
"""
Image Generation Model & Prompt Comparison Tester
==================================================

Directly calls Cloudflare Workers AI to compare image generation across:
  - Different models (SDXL-Lightning, SDXL Base, DreamShaper, FLUX.1)
  - Different prompt styles (Realistic, Kawaii, Duolingo, Flat, Watercolor, 3D Clay, Pixel Art, Line Art)
  - Different configuration parameters (guidance scale, num_steps)
  - Different test words from the vocabulary

Outputs:
  - All generated images saved to test_images/<timestamp>/
  - An HTML comparison report: test_images/<timestamp>/report.html
  - Console summary with timing stats

Usage:
  # Full comparison: 4 models × 8 prompts × 5 words = 160 images
  python test_image_generation.py --mode full

  # Quick test: 2 models × 3 prompts × 3 words = 18 images
  python test_image_generation.py --mode quick

  # Compare all models for one word
  python test_image_generation.py --mode models --word cat

  # Compare all prompts for one word with one model
  python test_image_generation.py --mode prompts --word cat

  # Compare guidance/steps for one word
  python test_image_generation.py --mode params --word cat

  # Custom single test
  python test_image_generation.py --mode single --word dog --model sdxl-lightning --prompt "a cute {word}, cartoon style"

  # Custom multi-word test
  python test_image_generation.py --mode custom --words "cat,dog,apple,car" --models "sdxl-lightning,flux" --prompts "realistic,kawaii"
"""

import argparse
import asyncio
import base64
import json
import mimetypes
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    import httpx
except ImportError:
    print("ERROR: httpx is required. Install with: pip install httpx")
    sys.exit(1)


# ── Configuration ──────────────────────────────────────────────────────────────

# Cloudflare API credentials (reads from env or .env.local)
CF_ACCOUNT_ID = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
CF_API_TOKEN = os.environ.get("CLOUDFLARE_API_TOKEN", "")

# Try loading from frontend .env.local if not set
if not CF_ACCOUNT_ID or not CF_API_TOKEN:
    env_path = Path(__file__).parent.parent / "MCSCaptsoneProject-frontend" / ".env.local"
    if not env_path.exists():
        env_path = Path(__file__).parent / ".." / "MCSCaptsoneProject-frontend" / ".env.local"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith("CLOUDFLARE_ACCOUNT_ID="):
                CF_ACCOUNT_ID = line.split("=", 1)[1].strip()
            elif line.startswith("CLOUDFLARE_API_TOKEN="):
                CF_API_TOKEN = line.split("=", 1)[1].strip()


# ── Models ─────────────────────────────────────────────────────────────────────

MODELS = {
    "sdxl-lightning": {
        "id": "@cf/bytedance/stable-diffusion-xl-lightning",
        "name": "SDXL-Lightning",
        "default_steps": 4,
        "default_guidance": 7.5,
        "description": "Fast 4-step generation, good for rapid testing",
    },
    "sdxl-base": {
        "id": "@cf/stabilityai/stable-diffusion-xl-base-1.0",
        "name": "SDXL Base 1.0",
        "default_steps": 20,
        "default_guidance": 7.5,
        "description": "High quality, slower, 20 steps recommended",
    },
    "dreamshaper": {
        "id": "@cf/lykon/dreamshaper-8-lcm",
        "name": "DreamShaper 8 LCM",
        "default_steps": 8,
        "default_guidance": 7.5,
        "description": "Creative/artistic, 8 steps, good for stylized images",
    },
    "flux": {
        "id": "@cf/black-forest-labs/flux-1-schnell",
        "name": "FLUX.1 Schnell",
        "default_steps": 4,
        "default_guidance": 7.5,
        "description": "Newest model, fast 4-step, often best quality",
    },
    "flux-2-dev": {
        "id": "@cf/black-forest-labs/flux-2-dev",
        "name": "FLUX.2 Dev",
        "default_steps": 20,
        "default_guidance": 7.5,
        "description": "High quality, multi-reference support",
    },
    "flux-2-klein-9b": {
        "id": "@cf/black-forest-labs/flux-2-klein-9b",
        "name": "FLUX.2 Klein 9B",
        "default_steps": 4,
        "default_guidance": 7.5,
        "description": "Ultra-fast distilled 9B, state-of-the-art quality",
    },
    "flux-2-klein-4b": {
        "id": "@cf/black-forest-labs/flux-2-klein-4b",
        "name": "FLUX.2 Klein 4B",
        "default_steps": 4,
        "default_guidance": 7.5,
        "description": "Ultra-fast distilled 4B, real-time generation",
    },
    "lucid-origin": {
        "id": "@cf/leonardo/lucid-origin",
        "name": "Leonardo Lucid Origin",
        "default_steps": 8,
        "default_guidance": 7.5,
        "description": "Most prompt-responsive, versatile styles",
    },
    "phoenix": {
        "id": "@cf/leonardo/phoenix-1.0",
        "name": "Leonardo Phoenix 1.0",
        "default_steps": 8,
        "default_guidance": 7.5,
        "description": "Exceptional prompt adherence, coherent text",
    },
}

# ── Prompt Presets ─────────────────────────────────────────────────────────────

PROMPT_PRESETS = {
    "realistic": {
        "name": "Realistic Product Photo",
        "prompt": "a single {word}, realistic, high quality product photo, centered on a pure white background, soft studio lighting, clean and bright, children educational flashcard, clear and recognizable, no text, no label",
        "negative_prompt": "cartoon, emoji, vector, flat, illustration, drawing, sketch, anime, manga, 3D render, text, letters, words, watermark, blurry, noisy, multiple objects, busy background, human, person, fingers, hands, face on object, anthropomorphic, dark, moody, scary",
    },
    "kawaii": {
        "name": "Kawaii Cartoon",
        "prompt": "a cute kawaii {word}, chibi style, adorable round shape, pastel colors, simple clean illustration, white background, children sticker design, no text",
        "negative_prompt": "realistic, photograph, dark, scary, complex background, text, letters, watermark, human, person",
    },
    "duolingo": {
        "name": "Duolingo Style",
        "prompt": "a {word}, cute simple illustration, bold outlines, flat bright colors, friendly cartoon style like Duolingo, white background, educational flashcard, no text, no label",
        "negative_prompt": "realistic, photograph, 3D, dark, scary, complex shading, text, letters, watermark, human face",
    },
    "flat": {
        "name": "Flat Icon",
        "prompt": "a {word} flat design icon, minimal vector style, solid colors, centered on white background, clean simple shapes, app icon style, no text",
        "negative_prompt": "realistic, photograph, 3D, shadow, gradient, complex, detailed, text, letters, busy background",
    },
    "watercolor": {
        "name": "Watercolor",
        "prompt": "a beautiful watercolor painting of a {word}, soft delicate brushstrokes, gentle pastel colors, white paper background, children book illustration style, artistic, no text",
        "negative_prompt": "photograph, digital, harsh colors, dark, scary, text, letters, watermark, multiple objects",
    },
    "3d-clay": {
        "name": "3D Clay / Pixar",
        "prompt": "a {word}, cute 3D rendered object, soft lighting, clay material, rounded shapes, centered on light gray background, Pixar style, children friendly, no text",
        "negative_prompt": "flat, 2D, sketch, photograph, dark, scary, text, letters, watermark, realistic texture",
    },
    "pixel-art": {
        "name": "Pixel Art",
        "prompt": "a {word} in pixel art style, 16-bit retro game sprite, clean pixels, bright colors, white background, centered, cute, no text",
        "negative_prompt": "realistic, photograph, blurry, smooth, gradient, text, letters, 3D, dark",
    },
    "line-art": {
        "name": "Line Art",
        "prompt": "a {word}, minimal line art drawing, single continuous line, black ink on white background, simple elegant, centered, no text",
        "negative_prompt": "color, realistic, photograph, complex, detailed shading, text, letters, multiple objects, busy",
    },
}

# ── Test Words ─────────────────────────────────────────────────────────────────

TEST_WORDS = {
    # Core test set — diverse categories for meaningful comparison
    "cat": {"en": "cat", "cn": "貓", "category": "Animals"},
    "dog": {"en": "dog", "cn": "狗", "category": "Animals"},
    "elephant": {"en": "elephant", "cn": "大象", "category": "Animals"},
    "butterfly": {"en": "butterfly", "cn": "蝴蝶", "category": "Animals"},
    "apple": {"en": "apple", "cn": "蘋果", "category": "Food"},
    "pizza": {"en": "pizza", "cn": "薄餅", "category": "Food"},
    "ice cream": {"en": "ice cream", "cn": "雪糕", "category": "Food"},
    "car": {"en": "car", "cn": "車", "category": "Transportation"},
    "airplane": {"en": "airplane", "cn": "飛機", "category": "Transportation"},
    "teddy bear": {"en": "teddy bear", "cn": "熊仔", "category": "Toys"},
    "balloon": {"en": "balloon", "cn": "氣球", "category": "Toys"},
    "tree": {"en": "tree", "cn": "樹", "category": "Nature"},
    "flower": {"en": "flower", "cn": "花", "category": "Nature"},
    "pencil": {"en": "pencil", "cn": "鉛筆", "category": "Stationery"},
    "book": {"en": "book", "cn": "書", "category": "Household"},
    "umbrella": {"en": "umbrella", "cn": "遮", "category": "Household"},
    "camera": {"en": "camera", "cn": "相機", "category": "Electronics"},
    "hat": {"en": "hat", "cn": "帽", "category": "Clothing"},
    "house": {"en": "house", "cn": "屋企", "category": "Places"},
    "bicycle": {"en": "bicycle", "cn": "單車", "category": "Transportation"},
}

# Guidance scale values to test
GUIDANCE_VALUES = [1.0, 3.0, 5.0, 7.5, 10.0, 15.0, 20.0]

# Step count values to test
STEPS_VALUES = [1, 2, 4, 8, 12, 20]


# ── Cloudflare API ─────────────────────────────────────────────────────────────

# Models that require multipart form data instead of JSON
MULTIPART_MODELS = {
    "@cf/black-forest-labs/flux-2-dev",
    "@cf/black-forest-labs/flux-2-klein-9b",
    "@cf/black-forest-labs/flux-2-klein-4b",
}


async def generate_image(
    client: httpx.AsyncClient,
    prompt: str,
    negative_prompt: str,
    model_id: str,
    guidance: float = 7.5,
    num_steps: int = 4,
    width: int = 512,
    height: int = 512,
    timeout: float = 60.0,
) -> tuple[Optional[bytes], float, str]:
    """
    Call Cloudflare Workers AI to generate an image.
    Returns (image_bytes, elapsed_seconds, error_message).
    """
    if not CF_ACCOUNT_ID or not CF_API_TOKEN:
        return None, 0.0, "Missing CLOUDFLARE_ACCOUNT_ID or CLOUDFLARE_API_TOKEN"

    url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/ai/run/{model_id}"
    auth_header = {"Authorization": f"Bearer {CF_API_TOKEN}"}

    use_multipart = model_id in MULTIPART_MODELS

    t0 = time.time()
    try:
        if use_multipart:
            # Newer models (FLUX.2, Leonardo) require multipart form data
            form_data = {
                "prompt": prompt,
                "width": str(width),
                "height": str(height),
                "guidance": str(guidance),
                "num_steps": str(num_steps),
            }
            if negative_prompt:
                form_data["negative_prompt"] = negative_prompt
            resp = await client.post(url, data=form_data, headers=auth_header, timeout=timeout)
        else:
            # Classic models use JSON body
            headers = {**auth_header, "Content-Type": "application/json"}
            payload = {
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "width": width,
                "height": height,
                "guidance": guidance,
                "num_steps": num_steps,
            }
            resp = await client.post(url, json=payload, headers=headers, timeout=timeout)

        elapsed = time.time() - t0

        if resp.status_code != 200:
            error_text = resp.text[:200]
            return None, elapsed, f"HTTP {resp.status_code}: {error_text}"

        content_type = resp.headers.get("content-type", "")

        if "image/" in content_type:
            image_bytes = resp.content
        else:
            # JSON response with base64 image
            try:
                data = resp.json()
                b64 = data.get("result", {}).get("image", "")
                if not b64:
                    return None, elapsed, "JSON response missing result.image"
                image_bytes = base64.b64decode(b64)
            except Exception as e:
                return None, elapsed, f"Failed to parse JSON response: {e}"

        if len(image_bytes) < 1000:
            return None, elapsed, f"Image too small ({len(image_bytes)} bytes)"

        return image_bytes, elapsed, ""

    except httpx.TimeoutException:
        elapsed = time.time() - t0
        return None, elapsed, f"Timeout after {elapsed:.1f}s"
    except Exception as e:
        elapsed = time.time() - t0
        return None, elapsed, str(e)


# ── Test Result ────────────────────────────────────────────────────────────────

class TestResult:
    def __init__(
        self,
        word: str,
        word_cn: str,
        model_key: str,
        model_name: str,
        prompt_key: str,
        prompt_name: str,
        prompt_text: str,
        negative_prompt: str,
        guidance: float,
        steps: int,
        image_path: Optional[str],
        elapsed: float,
        error: str,
        file_size: int = 0,
    ):
        self.word = word
        self.word_cn = word_cn
        self.model_key = model_key
        self.model_name = model_name
        self.prompt_key = prompt_key
        self.prompt_name = prompt_name
        self.prompt_text = prompt_text
        self.negative_prompt = negative_prompt
        self.guidance = guidance
        self.steps = steps
        self.image_path = image_path
        self.elapsed = elapsed
        self.error = error
        self.file_size = file_size

    @property
    def success(self) -> bool:
        return self.image_path is not None and not self.error


# ── Test Runner ────────────────────────────────────────────────────────────────

class ImageTester:
    def __init__(self, output_dir: str, concurrency: int = 2):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.concurrency = concurrency
        self.results: list[TestResult] = []
        self.semaphore = asyncio.Semaphore(concurrency)

    def _build_image_src(self, image_path: Optional[str]) -> Optional[str]:
        """Embed images into the report so the HTML stays portable."""
        if not image_path:
            return None

        image_file = self.output_dir / image_path
        if not image_file.exists():
            return None

        mime_type, _ = mimetypes.guess_type(str(image_file))
        if not mime_type:
            mime_type = "image/jpeg"

        encoded = base64.b64encode(image_file.read_bytes()).decode("ascii")
        return f"data:{mime_type};base64,{encoded}"

    async def run_single_test(
        self,
        client: httpx.AsyncClient,
        word: str,
        word_cn: str,
        model_key: str,
        prompt_key: str,
        guidance: float,
        steps: int,
        custom_prompt: Optional[str] = None,
        custom_neg_prompt: Optional[str] = None,
        tag: str = "",
    ) -> TestResult:
        """Run a single image generation test."""
        model = MODELS[model_key]
        preset = PROMPT_PRESETS.get(prompt_key, PROMPT_PRESETS["realistic"])

        prompt_text = custom_prompt or preset["prompt"]
        neg_prompt_text = custom_neg_prompt or preset["negative_prompt"]

        # Replace {word} placeholder
        prompt_filled = prompt_text.replace("{word}", word)
        neg_prompt_filled = neg_prompt_text.replace("{word}", word)

        # Generate filename
        safe_word = word.replace(" ", "_").replace("/", "_")
        tag_suffix = f"_{tag}" if tag else ""
        filename = f"{safe_word}__{model_key}__{prompt_key}__g{guidance}__s{steps}{tag_suffix}.jpg"
        filepath = self.output_dir / filename

        async with self.semaphore:
            print(f"  ⏳ Generating: {word} | {model['name']} | {preset['name']} | g={guidance} s={steps}")
            image_bytes, elapsed, error = await generate_image(
                client,
                prompt=prompt_filled,
                negative_prompt=neg_prompt_filled,
                model_id=model["id"],
                guidance=guidance,
                num_steps=steps,
            )

            result = TestResult(
                word=word,
                word_cn=word_cn,
                model_key=model_key,
                model_name=model["name"],
                prompt_key=prompt_key,
                prompt_name=preset["name"],
                prompt_text=prompt_filled,
                negative_prompt=neg_prompt_filled,
                guidance=guidance,
                steps=steps,
                image_path=None,
                elapsed=elapsed,
                error=error,
            )

            if image_bytes and not error:
                filepath.write_bytes(image_bytes)
                result.image_path = filename
                result.file_size = len(image_bytes)
                print(f"  ✅ Done: {word} | {model['name']} | {elapsed:.1f}s | {len(image_bytes)//1024}KB")
            else:
                print(f"  ❌ Failed: {word} | {model['name']} | {error}")

            self.results.append(result)
            return result

    async def run_tests(self, test_specs: list[dict]):
        """Run multiple tests with concurrency control."""
        async with httpx.AsyncClient() as client:
            tasks = []
            for spec in test_specs:
                task = self.run_single_test(
                    client,
                    word=spec["word"],
                    word_cn=spec.get("word_cn", ""),
                    model_key=spec["model"],
                    prompt_key=spec.get("prompt", "realistic"),
                    guidance=spec.get("guidance", MODELS[spec["model"]]["default_guidance"]),
                    steps=spec.get("steps", MODELS[spec["model"]]["default_steps"]),
                    custom_prompt=spec.get("custom_prompt"),
                    custom_neg_prompt=spec.get("custom_neg_prompt"),
                    tag=spec.get("tag", ""),
                )
                tasks.append(task)
            await asyncio.gather(*tasks)

    def generate_report(self) -> str:
                """Generate an HTML comparison report."""
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                total = len(self.results)
                success = sum(1 for r in self.results if r.success)
                failed = total - success
                avg_time = sum(r.elapsed for r in self.results) / max(total, 1)
                total_time = sum(r.elapsed for r in self.results)

                by_word: dict[str, list[TestResult]] = {}
                for result in self.results:
                        by_word.setdefault(result.word, []).append(result)

                all_models = sorted(set(r.model_key for r in self.results))
                all_prompts = sorted(set(r.prompt_key for r in self.results))

                html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>Image Generation Comparison Report</title>
<style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif; background: #f5f5f7; color: #1d1d1f; padding: 24px; }}
    .header {{ text-align: center; margin-bottom: 32px; }}
    .header h1 {{ font-size: 28px; font-weight: 700; margin-bottom: 8px; }}
    .header .subtitle {{ color: #86868b; font-size: 14px; }}
    .stats-bar {{ display: flex; justify-content: center; gap: 32px; padding: 16px; margin-bottom: 24px; background: white; border-radius: 16px; box-shadow: 0 2px 10px rgba(0,0,0,0.04); }}
    .stat {{ text-align: center; }}
    .stat .value {{ font-size: 28px; font-weight: 700; }}
    .stat .label {{ font-size: 12px; color: #86868b; margin-top: 2px; }}
    .stat.success .value {{ color: #34c759; }}
    .stat.failed .value {{ color: #ff3b30; }}
    .stat.time .value {{ color: #007aff; }}
    .section {{ margin-bottom: 32px; }}
    .section-title {{ font-size: 20px; font-weight: 600; margin-bottom: 16px; padding-bottom: 8px; border-bottom: 2px solid #e5e5ea; display: flex; align-items: center; gap: 8px; }}
    .section-title .word-cn {{ font-size: 16px; color: #86868b; }}
    .compare-grid {{ display: grid; gap: 16px; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); }}
    .compare-grid.cols-2 {{ grid-template-columns: repeat(2, 1fr); }}
    .compare-grid.cols-3 {{ grid-template-columns: repeat(3, 1fr); }}
    .compare-grid.cols-4 {{ grid-template-columns: repeat(4, 1fr); }}
    .card {{ background: white; border-radius: 16px; overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,0.06); transition: transform 0.2s, box-shadow 0.2s; }}
    .card:hover {{ transform: translateY(-3px); box-shadow: 0 8px 24px rgba(0,0,0,0.1); }}
    .card img {{ width: 100%; aspect-ratio: 1; object-fit: cover; display: block; background: #f5f5f7; }}
    .card .card-body {{ padding: 12px 14px; }}
    .card .card-title {{ font-size: 14px; font-weight: 600; margin-bottom: 6px; }}
    .card .card-meta {{ font-size: 11px; color: #86868b; line-height: 1.7; }}
    .badge {{ display: inline-block; padding: 2px 8px; border-radius: 6px; font-size: 10px; font-weight: 600; }}
    .badge-model {{ background: #f0e6ff; color: #7c3aed; }}
    .badge-prompt {{ background: #e6f7ff; color: #0077cc; }}
    .badge-success {{ background: #d4edda; color: #155724; }}
    .badge-error {{ background: #f8d7da; color: #721c24; }}
    .badge-time {{ background: #fff3cd; color: #856404; }}
    .badge-size {{ background: #e8f5e9; color: #2e7d32; }}
    .badge-guidance {{ background: #fff0f6; color: #c41d7f; }}
    .badge-steps {{ background: #f6ffed; color: #389e0d; }}
    .prompt-text {{ font-size: 10px; color: #aaa; margin-top: 6px; padding: 6px 8px; background: #fafafa; border-radius: 6px; word-break: break-all; max-height: 48px; overflow: hidden; line-height: 1.5; }}
    .error-card {{ padding: 24px; text-align: center; background: #fff5f5; border: 2px dashed #ffccc7; border-radius: 16px; color: #cf1322; }}
    .error-card .error-icon {{ font-size: 48px; margin-bottom: 8px; }}
    .error-card .error-msg {{ font-size: 12px; color: #999; margin-top: 4px; }}
    .summary-table {{ width: 100%; border-collapse: collapse; background: white; border-radius: 12px; overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,0.04); }}
    .summary-table th {{ background: #f5f5f7; padding: 10px 14px; font-size: 12px; text-align: left; color: #86868b; font-weight: 600; }}
    .summary-table td {{ padding: 10px 14px; font-size: 13px; border-top: 1px solid #f0f0f0; }}
    .summary-table tr:hover td {{ background: #fafafa; }}
    .legend {{ display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 16px; }}
    .legend-item {{ display: flex; align-items: center; gap: 4px; font-size: 12px; color: #666; }}
    @media (max-width: 768px) {{
        .compare-grid {{ grid-template-columns: repeat(2, 1fr) !important; gap: 10px; }}
        .stats-bar {{ flex-wrap: wrap; gap: 16px; }}
    }}
</style>
</head>
<body>
<div class="header">
    <h1>Image Generation Comparison Report</h1>
    <p class="subtitle">Generated {timestamp} · {total} images across {len(all_models)} model(s) × {len(all_prompts)} prompt(s)</p>
</div>
<div class="stats-bar">
    <div class="stat"><div class="value">{total}</div><div class="label">Total Tests</div></div>
    <div class="stat success"><div class="value">{success}</div><div class="label">Successful</div></div>
    <div class="stat failed"><div class="value">{failed}</div><div class="label">Failed</div></div>
    <div class="stat time"><div class="value">{avg_time:.1f}s</div><div class="label">Avg Time</div></div>
    <div class="stat"><div class="value">{total_time:.0f}s</div><div class="label">Total Time</div></div>
</div>
"""

                html += '<div class="legend">\n'
                for model_key in all_models:
                        html += f'  <div class="legend-item"><span class="badge badge-model">{MODELS[model_key]["name"]}</span></div>\n'
                html += '</div>\n'

                num_variants = max(len(all_models), len(all_prompts), 1)
                cols_cls = f"cols-{min(num_variants, 4)}" if num_variants <= 4 else ""

                for word, word_results in by_word.items():
                        word_cn = word_results[0].word_cn if word_results else ""
                        html += f'<div class="section">\n'
                        html += f'  <div class="section-title">{word} <span class="word-cn">{word_cn}</span></div>\n'
                        html += f'  <div class="compare-grid {cols_cls}">\n'

                        word_results.sort(key=lambda r: (r.model_key, r.prompt_key, r.guidance, r.steps))

                        for result in word_results:
                                image_src = self._build_image_src(result.image_path)
                                if result.success and image_src:
                                        html += f"""    <div class="card">
            <img src="{image_src}" alt="{result.word}" loading="lazy" />
            <div class="card-body">
                <div class="card-title">{result.word} ({result.word_cn})</div>
                <div class="card-meta">
                    <span class="badge badge-model">{result.model_name}</span>
                    <span class="badge badge-prompt">{result.prompt_name}</span><br/>
                    <span class="badge badge-guidance">g={result.guidance}</span>
                    <span class="badge badge-steps">steps={result.steps}</span>
                    <span class="badge badge-time">{result.elapsed:.1f}s</span>
                    <span class="badge badge-size">{result.file_size//1024}KB</span>
                </div>
                <div class="prompt-text">{result.prompt_text[:200]}</div>
            </div>
        </div>\n"""
                                elif result.success and result.image_path:
                                        html += f"""    <div class="error-card">
            <div class="error-icon">⚠️</div>
            <div><strong>{result.word}</strong></div>
            <div><span class="badge badge-model">{result.model_name}</span> <span class="badge badge-prompt">{result.prompt_name}</span></div>
            <div class="error-msg">Expected image file is missing: {result.image_path}</div>
        </div>\n"""
                                else:
                                        message = result.error[:120] if result.error else "Unknown error"
                                        html += f"""    <div class="error-card">
            <div class="error-icon">❌</div>
            <div><strong>{result.word}</strong></div>
            <div><span class="badge badge-model">{result.model_name}</span> <span class="badge badge-prompt">{result.prompt_name}</span></div>
            <div class="error-msg">{message}</div>
        </div>\n"""

                        html += '  </div>\n</div>\n'

                html += """
<div class="section">
    <div class="section-title">Detailed Results</div>
    <table class="summary-table">
        <thead><tr>
            <th>#</th><th>Word</th><th>Model</th><th>Prompt</th>
            <th>Guidance</th><th>Steps</th><th>Time</th><th>Size</th><th>Status</th>
        </tr></thead>
        <tbody>
"""
                for index, result in enumerate(self.results, 1):
                        status = '<span class="badge badge-success">✓ OK</span>' if result.success else f'<span class="badge badge-error">✗ {result.error[:40]}</span>'
                        size = f"{result.file_size // 1024}KB" if result.file_size else "—"
                        html += f"""      <tr>
                <td>{index}</td><td>{result.word} {result.word_cn}</td><td>{result.model_name}</td><td>{result.prompt_name}</td>
                <td>{result.guidance}</td><td>{result.steps}</td><td>{result.elapsed:.1f}s</td><td>{size}</td><td>{status}</td>
            </tr>\n"""

                html += """    </tbody>
    </table>
</div>

<div class="section">
    <div class="section-title">Performance by Model</div>
    <table class="summary-table">
        <thead><tr><th>Model</th><th>Tests</th><th>Success</th><th>Failed</th><th>Avg Time</th><th>Avg Size</th></tr></thead>
        <tbody>
"""
                for model_key in all_models:
                        model_results = [r for r in self.results if r.model_key == model_key]
                        total_results = len(model_results)
                        successful_results = sum(1 for r in model_results if r.success)
                        failed_results = total_results - successful_results
                        avg_model_time = sum(r.elapsed for r in model_results) / max(total_results, 1)
                        avg_model_size = sum(r.file_size for r in model_results if r.success) / max(successful_results, 1)
                        html += f"""      <tr>
                <td><span class="badge badge-model">{MODELS[model_key]['name']}</span></td>
                <td>{total_results}</td><td>{successful_results}</td><td>{failed_results}</td>
                <td>{avg_model_time:.1f}s</td><td>{avg_model_size/1024:.0f}KB</td>
            </tr>\n"""

                html += """    </tbody>
    </table>
</div>

<div class="section">
    <div class="section-title">Performance by Prompt Style</div>
    <table class="summary-table">
        <thead><tr><th>Prompt</th><th>Tests</th><th>Success</th><th>Failed</th><th>Avg Time</th><th>Avg Size</th></tr></thead>
        <tbody>
"""
                for prompt_key in all_prompts:
                        prompt_results = [r for r in self.results if r.prompt_key == prompt_key]
                        total_results = len(prompt_results)
                        successful_results = sum(1 for r in prompt_results if r.success)
                        failed_results = total_results - successful_results
                        avg_prompt_time = sum(r.elapsed for r in prompt_results) / max(total_results, 1)
                        avg_prompt_size = sum(r.file_size for r in prompt_results if r.success) / max(successful_results, 1)
                        prompt_name = PROMPT_PRESETS.get(prompt_key, {}).get("name", prompt_key)
                        html += f"""      <tr>
                <td><span class="badge badge-prompt">{prompt_name}</span></td>
                <td>{total_results}</td><td>{successful_results}</td><td>{failed_results}</td>
                <td>{avg_prompt_time:.1f}s</td><td>{avg_prompt_size/1024:.0f}KB</td>
            </tr>\n"""

                html += """    </tbody>
    </table>
</div>

</body>
</html>"""

                report_path = self.output_dir / "report.html"
                report_path.write_text(html, encoding="utf-8")
                return str(report_path)

    def print_summary(self):
        """Print a console summary of all results."""
        total = len(self.results)
        success = sum(1 for r in self.results if r.success)
        failed = total - success
        avg_time = sum(r.elapsed for r in self.results) / max(total, 1)

        print("\n" + "=" * 70)
        print(f"  IMAGE GENERATION TEST SUMMARY")
        print("=" * 70)
        print(f"  Total: {total}  |  ✅ Success: {success}  |  ❌ Failed: {failed}  |  ⏱ Avg: {avg_time:.1f}s")
        print("-" * 70)

        # Per-model summary
        models_seen = sorted(set(r.model_key for r in self.results))
        for mk in models_seen:
            mr = [r for r in self.results if r.model_key == mk]
            ms = sum(1 for r in mr if r.success)
            mt = sum(r.elapsed for r in mr) / max(len(mr), 1)
            print(f"  {MODELS[mk]['name']:25s}  OK: {ms}/{len(mr)}  Avg: {mt:.1f}s")

        print("-" * 70)

        # Per-prompt summary
        prompts_seen = sorted(set(r.prompt_key for r in self.results))
        for pk in prompts_seen:
            pr = [r for r in self.results if r.prompt_key == pk]
            ps = sum(1 for r in pr if r.success)
            pt = sum(r.elapsed for r in pr) / max(len(pr), 1)
            pname = PROMPT_PRESETS.get(pk, {}).get("name", pk)
            print(f"  {pname:25s}  OK: {ps}/{len(pr)}  Avg: {pt:.1f}s")

        if failed > 0:
            print("-" * 70)
            print("  ERRORS:")
            for r in self.results:
                if not r.success:
                    print(f"    - {r.word} | {r.model_name} | {r.prompt_name} : {r.error[:80]}")

        print("=" * 70)
        print(f"  Output dir: {self.output_dir}")
        report = self.output_dir / "report.html"
        if report.exists():
            print(f"  Report: {report}")
        print("=" * 70 + "\n")


# ── Test Mode Builders ─────────────────────────────────────────────────────────

def build_full_test(words: list[str], models: list[str], prompts: list[str]) -> list[dict]:
    """Full matrix: every model × every prompt × every word."""
    specs = []
    for w in words:
        wd = TEST_WORDS.get(w, {"en": w, "cn": "", "category": ""})
        for m in models:
            for p in prompts:
                specs.append({
                    "word": wd["en"],
                    "word_cn": wd.get("cn", ""),
                    "model": m,
                    "prompt": p,
                })
    return specs


def build_model_compare(word: str, prompts: list[str]) -> list[dict]:
    """Compare all models for a single word across selected prompts."""
    wd = TEST_WORDS.get(word, {"en": word, "cn": "", "category": ""})
    specs = []
    for p in prompts:
        for mk in MODELS:
            specs.append({
                "word": wd["en"],
                "word_cn": wd.get("cn", ""),
                "model": mk,
                "prompt": p,
            })
    return specs


def build_prompt_compare(word: str, model: str) -> list[dict]:
    """Compare all prompt styles for a single word with one model."""
    wd = TEST_WORDS.get(word, {"en": word, "cn": "", "category": ""})
    specs = []
    for pk in PROMPT_PRESETS:
        specs.append({
            "word": wd["en"],
            "word_cn": wd.get("cn", ""),
            "model": model,
            "prompt": pk,
        })
    return specs


def build_param_compare(word: str, model: str, prompt: str) -> list[dict]:
    """Compare different guidance and step values."""
    wd = TEST_WORDS.get(word, {"en": word, "cn": "", "category": ""})
    specs = []
    # Vary guidance with fixed steps
    base_steps = MODELS[model]["default_steps"]
    for g in GUIDANCE_VALUES:
        specs.append({
            "word": wd["en"],
            "word_cn": wd.get("cn", ""),
            "model": model,
            "prompt": prompt,
            "guidance": g,
            "steps": base_steps,
            "tag": f"guidance_{g}",
        })
    # Vary steps with fixed guidance
    base_guidance = MODELS[model]["default_guidance"]
    for s in STEPS_VALUES:
        specs.append({
            "word": wd["en"],
            "word_cn": wd.get("cn", ""),
            "model": model,
            "prompt": prompt,
            "guidance": base_guidance,
            "steps": s,
            "tag": f"steps_{s}",
        })
    return specs


# ── CLI ────────────────────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(
        description="Compare image generation across models, prompts, and configurations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python test_image_generation.py --mode quick
  python test_image_generation.py --mode full
  python test_image_generation.py --mode models --word cat
  python test_image_generation.py --mode prompts --word dog --model sdxl-lightning
  python test_image_generation.py --mode params --word apple --model flux
  python test_image_generation.py --mode single --word cat --model flux --prompt "a cute {word} illustration"
  python test_image_generation.py --mode custom --words "cat,dog,apple" --models "sdxl-lightning,flux" --prompts "realistic,kawaii,duolingo"
        """,
    )
    parser.add_argument(
        "--mode",
        choices=["quick", "full", "models", "prompts", "params", "single", "custom"],
        default="quick",
        help="Test mode (default: quick)",
    )
    parser.add_argument("--word", type=str, default="cat", help="Word to test (for single/models/prompts/params modes)")
    parser.add_argument("--words", type=str, default="", help="Comma-separated words (for custom mode)")
    parser.add_argument(
        "--model",
        type=str,
        default="sdxl-lightning",
        choices=list(MODELS.keys()),
        help="Model key (for prompts/params/single modes)",
    )
    parser.add_argument("--models", type=str, default="", help="Comma-separated model keys (for custom mode)")
    parser.add_argument("--prompt", type=str, default="realistic", help="Prompt preset key or custom prompt text with {word}")
    parser.add_argument("--prompts", type=str, default="", help="Comma-separated prompt preset keys (for custom mode)")
    parser.add_argument("--neg-prompt", type=str, default="", help="Custom negative prompt (for single mode)")
    parser.add_argument("--guidance", type=float, default=0, help="Guidance scale override (0 = use model default)")
    parser.add_argument("--steps", type=int, default=0, help="Steps override (0 = use model default)")
    parser.add_argument("--concurrency", type=int, default=2, help="Max concurrent API calls (default: 2)")
    parser.add_argument("--output", type=str, default="", help="Output directory (default: test_images/<timestamp>)")
    return parser.parse_args()


async def main():
    args = parse_args()

    # Check credentials
    if not CF_ACCOUNT_ID or not CF_API_TOKEN:
        print("❌ ERROR: Cloudflare credentials not found.")
        print("   Set CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN environment variables,")
        print("   or ensure MCSCaptsoneProject-frontend/.env.local exists with these values.")
        sys.exit(1)

    # Output directory
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = args.output or f"test_images/{timestamp}"

    print(f"\n🖼️  Image Generation Comparison Tester")
    print(f"   Mode: {args.mode}")
    print(f"   Output: {output_dir}")
    print(f"   Concurrency: {args.concurrency}")
    print()

    tester = ImageTester(output_dir, concurrency=args.concurrency)

    # Build test specs based on mode
    specs: list[dict] = []

    if args.mode == "quick":
        # 2 models × 3 prompts × 3 words = 18 images
        quick_words = ["cat", "apple", "car"]
        quick_models = ["sdxl-lightning", "flux"]
        quick_prompts = ["realistic", "kawaii", "duolingo"]
        specs = build_full_test(quick_words, quick_models, quick_prompts)
        print(f"   Quick test: {len(quick_words)} words × {len(quick_models)} models × {len(quick_prompts)} prompts = {len(specs)} images\n")

    elif args.mode == "full":
        # All models × all prompts × 5 words
        full_words = ["cat", "apple", "car", "teddy bear", "flower"]
        full_models = list(MODELS.keys())
        full_prompts = list(PROMPT_PRESETS.keys())
        specs = build_full_test(full_words, full_models, full_prompts)
        print(f"   Full test: {len(full_words)} words × {len(full_models)} models × {len(full_prompts)} prompts = {len(specs)} images\n")

    elif args.mode == "models":
        # Compare all 4 models for one word
        specs = build_model_compare(args.word, ["realistic"])
        print(f"   Model comparison: '{args.word}' across {len(MODELS)} models\n")

    elif args.mode == "prompts":
        # Compare all prompt styles for one word
        specs = build_prompt_compare(args.word, args.model)
        print(f"   Prompt comparison: '{args.word}' with {MODELS[args.model]['name']} across {len(PROMPT_PRESETS)} styles\n")

    elif args.mode == "params":
        # Compare guidance/steps for one word
        specs = build_param_compare(args.word, args.model, args.prompt)
        print(f"   Parameter sweep: '{args.word}' with {MODELS[args.model]['name']}\n")
        print(f"   Guidance values: {GUIDANCE_VALUES}")
        print(f"   Steps values: {STEPS_VALUES}\n")

    elif args.mode == "single":
        # Single image test
        wd = TEST_WORDS.get(args.word, {"en": args.word, "cn": "", "category": ""})
        is_custom_prompt = "{word}" in args.prompt and args.prompt not in PROMPT_PRESETS
        spec = {
            "word": wd["en"],
            "word_cn": wd.get("cn", ""),
            "model": args.model,
        }
        if is_custom_prompt:
            spec["prompt"] = "realistic"  # base key for naming
            spec["custom_prompt"] = args.prompt
            if args.neg_prompt:
                spec["custom_neg_prompt"] = args.neg_prompt
        else:
            spec["prompt"] = args.prompt if args.prompt in PROMPT_PRESETS else "realistic"

        if args.guidance > 0:
            spec["guidance"] = args.guidance
        if args.steps > 0:
            spec["steps"] = args.steps
        specs = [spec]
        print(f"   Single test: '{args.word}' with {MODELS[args.model]['name']}\n")

    elif args.mode == "custom":
        # Custom combination
        words = [w.strip() for w in args.words.split(",") if w.strip()] or ["cat"]
        models = [m.strip() for m in args.models.split(",") if m.strip()] or ["sdxl-lightning"]
        prompts = [p.strip() for p in args.prompts.split(",") if p.strip()] or ["realistic"]

        # Validate
        for m in models:
            if m not in MODELS:
                print(f"❌ Unknown model: {m}. Available: {', '.join(MODELS.keys())}")
                sys.exit(1)
        for p in prompts:
            if p not in PROMPT_PRESETS:
                print(f"❌ Unknown prompt preset: {p}. Available: {', '.join(PROMPT_PRESETS.keys())}")
                sys.exit(1)

        specs = build_full_test(words, models, prompts)
        print(f"   Custom test: {len(words)} words × {len(models)} models × {len(prompts)} prompts = {len(specs)} images\n")

    if not specs:
        print("❌ No test specifications generated. Check your arguments.")
        sys.exit(1)

    # Run all tests
    t_start = time.time()
    await tester.run_tests(specs)
    total_elapsed = time.time() - t_start

    print(f"\n  ⏱  Total wall time: {total_elapsed:.1f}s")

    # Generate HTML report
    report_path = tester.generate_report()
    print(f"  📊 Report generated: {report_path}")

    # Save test config as JSON
    config_path = Path(output_dir) / "test_config.json"
    config_path.write_text(json.dumps({
        "mode": args.mode,
        "timestamp": timestamp,
        "total_tests": len(specs),
        "concurrency": args.concurrency,
        "models": list(set(s["model"] for s in specs)),
        "prompts": list(set(s.get("prompt", "realistic") for s in specs)),
        "words": list(set(s["word"] for s in specs)),
        "wall_time": round(total_elapsed, 1),
    }, indent=2), encoding="utf-8")

    # Print summary
    tester.print_summary()

    print(f"  💡 Open the report:  open {report_path}")


if __name__ == "__main__":
    asyncio.run(main())
