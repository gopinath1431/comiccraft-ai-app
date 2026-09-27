"""Optional Gemini integration with a deterministic local fallback.

The app intentionally uses the Gemini REST API here instead of importing a
provider SDK. That keeps the FastAPI artifact lightweight and lets an owner
provide a normal GEMINI_API_KEY/GOOGLE_API_KEY later through Replit Secrets
or another environment-variable manager.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any


TEXT_MODEL = os.getenv("GEMINI_TEXT_MODEL", "gemini-2.5-flash")
IMAGE_MODEL = os.getenv("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image")
DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"


class GeminiError(RuntimeError):
    """A safe, user-facing error for optional Gemini calls."""


def get_gemini_api_key() -> str | None:
    return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")


def gemini_configured() -> bool:
    return bool(get_gemini_api_key())


def _endpoint(model: str) -> str:
    base_url = os.getenv("GEMINI_API_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    api_key = get_gemini_api_key()
    if not api_key:
        raise GeminiError("No Gemini API key is configured.")
    return f"{base_url}/models/{model}:generateContent?{urllib.parse.urlencode({'key': api_key})}"


def _post_json(model: str, body: dict[str, Any], *, timeout: int = 90) -> dict[str, Any]:
    request = urllib.request.Request(
        _endpoint(model),
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:600]
        raise GeminiError(f"Gemini request failed ({exc.code}): {detail}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise GeminiError(f"Gemini request could not be completed: {exc}") from exc

    if "error" in payload:
        raise GeminiError(str(payload["error"])[:600])
    return payload


def _response_parts(payload: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = payload.get("candidates") or []
    if not candidates:
        raise GeminiError("Gemini returned no candidates.")
    content = candidates[0].get("content") or {}
    return content.get("parts") or []


def _response_text(payload: dict[str, Any]) -> str:
    text = "".join(
        str(part.get("text", ""))
        for part in _response_parts(payload)
        if part.get("text")
    ).strip()
    if not text:
        raise GeminiError("Gemini returned an empty story outline.")
    return text


def _parse_json(text: str) -> dict[str, Any]:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.IGNORECASE)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end <= start:
        raise GeminiError("Gemini returned an outline that was not valid JSON.")
    try:
        value = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as exc:
        raise GeminiError(f"Gemini returned invalid outline JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise GeminiError("Gemini returned an outline in an unexpected format.")
    return value


def _outline_prompt(prompt: str, genre: str, visual_style: str, palette: str) -> str:
    return f"""
You are the story editor for ComicCraft, a three-panel comic creator.
Turn the user's story seed into a concise, cinematic comic outline.

Story seed: {prompt}
Genre: {genre}
Linework: {visual_style}
Palette: {palette}

Return JSON only, with exactly these keys:
{{
  "title": "short comic title",
  "logline": "one sentence",
  "character_bible": "stable appearance, clothing, age, silhouette, and defining props",
  "style_bible": "stable art direction, camera language, lighting, and palette",
  "panels": [
    {{
      "number": "01",
      "scene": "short scene label",
      "visual": "specific visual direction for the image",
      "dialogue": "short dialogue or thought balloon",
      "caption": "short caption",
      "tone": "setup"
    }},
    {{
      "number": "02",
      "scene": "short scene label",
      "visual": "specific visual direction for the image",
      "dialogue": "short dialogue or thought balloon",
      "caption": "short caption",
      "tone": "turn"
    }},
    {{
      "number": "03",
      "scene": "short scene label",
      "visual": "specific visual direction for the image",
      "dialogue": "short dialogue or thought balloon",
      "caption": "short caption",
      "tone": "cliffhanger"
    }}
  ]
}}

Keep the same main character description and art direction in all three panels.
Do not include markdown or extra keys.
""".strip()


def _normalize_outline(
    outline: dict[str, Any],
    *,
    genre: str,
    visual_style: str,
    palette: str,
) -> dict[str, Any]:
    raw_panels = outline.get("panels")
    if not isinstance(raw_panels, list) or not raw_panels:
        raise GeminiError("Gemini returned an outline without panels.")

    panels: list[dict[str, Any]] = []
    for index, raw_panel in enumerate(raw_panels[:3]):
        if not isinstance(raw_panel, dict):
            continue
        panels.append(
            {
                "number": f"{index + 1:02d}",
                "scene": str(raw_panel.get("scene") or f"Story beat {index + 1}"),
                "visual": str(raw_panel.get("visual") or "A cinematic comic frame."),
                "dialogue": str(raw_panel.get("dialogue") or "..."),
                "caption": str(raw_panel.get("caption") or "The story moves."),
                "tone": str(raw_panel.get("tone") or ["setup", "turn", "cliffhanger"][index]),
            }
        )
    if len(panels) != 3:
        raise GeminiError("Gemini returned fewer than three usable panels.")

    return {
        "title": str(outline.get("title") or "A ComicCraft story"),
        "logline": str(outline.get("logline") or ""),
        "genre": genre,
        "style": visual_style,
        "palette": palette,
        "character_bible": str(
            outline.get("character_bible")
            or "One recurring protagonist with a clear silhouette and consistent clothing."
        ),
        "style_bible": str(
            outline.get("style_bible")
            or f"{visual_style} linework with a {palette} limited palette."
        ),
        "panels": panels,
    }


def _image_prompt(outline: dict[str, Any], panel: dict[str, Any]) -> str:
    return f"""
Create one comic panel image for ComicCraft.

Character continuity bible:
{outline["character_bible"]}

Art style bible:
{outline["style_bible"]}

Panel {panel["number"]} — {panel["scene"]}:
{panel["visual"]}

Composition: portrait comic panel, clear foreground/midground/background,
strong readable silhouette, expressive staging, consistent character design.
Do not render any words, letters, captions, speech balloons, logos, or watermark;
the app will add text separately.
""".strip()


def _image_bytes(payload: dict[str, Any]) -> tuple[str, bytes]:
    for part in _response_parts(payload):
        inline = part.get("inlineData") or part.get("inline_data")
        if not inline:
            continue
        encoded = inline.get("data")
        if not encoded:
            continue
        mime_type = str(inline.get("mimeType") or inline.get("mime_type") or "image/png")
        try:
            return mime_type, base64.b64decode(encoded)
        except (ValueError, binascii.Error) as exc:
            raise GeminiError("Gemini returned an invalid panel image.") from exc
    raise GeminiError("Gemini returned no panel image.")


def _save_image(payload: dict[str, Any], output_dir: Path, panel_number: str) -> str:
    mime_type, data = _image_bytes(payload)
    extension = "jpg" if "jpeg" in mime_type or "jpg" in mime_type else "png"
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"comic-{uuid.uuid4().hex[:12]}-panel-{panel_number}.{extension}"
    (output_dir / filename).write_bytes(data)
    return f"/static/generated/{filename}"


async def generate_ai_comic(
    prompt: str,
    genre: str,
    visual_style: str,
    palette: str,
    output_dir: Path,
) -> dict[str, Any]:
    """Generate a story outline and three images with shared prompt bibles."""
    if not gemini_configured():
        raise GeminiError("No Gemini API key is configured.")

    outline_payload = await asyncio.to_thread(
        _post_json,
        TEXT_MODEL,
        {
            "contents": [{"role": "user", "parts": [{"text": _outline_prompt(prompt, genre, visual_style, palette)}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.85,
                "maxOutputTokens": 8192,
            },
        },
    )
    outline = _normalize_outline(
        _parse_json(_response_text(outline_payload)),
        genre=genre,
        visual_style=visual_style,
        palette=palette,
    )

    for panel in outline["panels"]:
        try:
            image_payload = await asyncio.to_thread(
                _post_json,
                IMAGE_MODEL,
                {
                    "contents": [
                        {
                            "role": "user",
                            "parts": [{"text": _image_prompt(outline, panel)}],
                        }
                    ],
                    "generationConfig": {"responseModalities": ["IMAGE"]},
                },
            )
            panel["image_url"] = _save_image(image_payload, output_dir, panel["number"])
            panel["image_alt"] = f"{outline['title']} panel {panel['number']}: {panel['scene']}"
        except GeminiError as exc:
            panel["image_url"] = ""
            panel["image_alt"] = ""
            panel["image_error"] = str(exc)

    outline["generation_mode"] = "AI"
    outline["provider"] = "Gemini"
    outline["status"] = "AI concept ready"
    return outline