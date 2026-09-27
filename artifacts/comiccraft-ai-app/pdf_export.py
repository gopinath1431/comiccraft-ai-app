"""Small PDF exporter for comic concepts."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from textwrap import wrap
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


def _draw_wrapped_text(
    pdf: canvas.Canvas,
    text: str,
    x: float,
    y: float,
    width: float,
    *,
    font: str = "Helvetica",
    size: float = 8,
    leading: float = 10,
    max_lines: int = 4,
) -> float:
    pdf.setFont(font, size)
    words = str(text or "").split()
    if not words:
        return y
    approximate_chars = max(12, int(width / (size * 0.52)))
    lines = wrap(" ".join(words), width=approximate_chars)[:max_lines]
    for line in lines:
        pdf.drawString(x, y, line)
        y -= leading
    return y


def _panel_image_path(image_url: str, base_dir: Path) -> Path | None:
    prefix = "/static/generated/"
    if not image_url.startswith(prefix):
        return None
    candidate = (base_dir / "static" / "generated" / image_url.removeprefix(prefix)).resolve()
    generated_dir = (base_dir / "static" / "generated").resolve()
    if generated_dir not in candidate.parents or not candidate.is_file():
        return None
    return candidate


def _draw_fallback_art(pdf: canvas.Canvas, x: float, y: float, width: float, height: float, index: int) -> None:
    colorset = [
        (colors.HexColor("#8ab7b0"), colors.HexColor("#8b80a8")),
        (colors.HexColor("#e65345"), colors.HexColor("#f2ca68")),
        (colors.HexColor("#8b80a8"), colors.HexColor("#f5f0e4")),
    ][index % 3]
    pdf.setFillColor(colorset[0])
    pdf.rect(x, y, width, height, fill=1, stroke=0)
    pdf.setFillColor(colorset[1])
    pdf.circle(x + width * (0.3 + index * 0.12), y + height * 0.67, min(width, height) * 0.13, fill=1, stroke=0)
    pdf.setFillColor(colors.HexColor("#22221e"))
    pdf.setLineWidth(1.4)
    pdf.line(x, y + height * 0.27, x + width, y + height * 0.37)
    pdf.setFillColor(colors.HexColor("#22221e"))
    pdf.rect(x + width * 0.58, y + height * 0.08, width * 0.2, height * 0.18, fill=1, stroke=0)


def build_comic_pdf(comic: dict[str, Any], base_dir: Path) -> bytes:
    """Render a single landscape letter page with all three comic panels."""
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=landscape(letter))
    page_width, page_height = landscape(letter)
    margin = 30

    pdf.setFillColor(colors.HexColor("#22221e"))
    pdf.setFont("Helvetica-Bold", 20)
    pdf.drawString(margin, page_height - margin - 4, str(comic.get("title") or "ComicCraft rough page"))
    pdf.setFont("Courier", 7)
    pdf.setFillColor(colors.HexColor("#b93831"))
    meta = f"{comic.get('generation_mode', 'DEMO_MODE')} / {comic.get('style', 'ink and wash')} / {comic.get('status', 'concept ready')}"
    pdf.drawRightString(page_width - margin, page_height - margin - 2, meta.upper())

    panels = list(comic.get("panels") or [])[:3]
    gap = 10
    panel_width = (page_width - 2 * margin - 2 * gap) / 3
    panel_height = page_height - 2 * margin - 54
    panel_y = margin + 17

    for index, panel in enumerate(panels):
        x = margin + index * (panel_width + gap)
        pdf.setStrokeColor(colors.HexColor("#22221e"))
        pdf.setLineWidth(1.2)
        pdf.setFillColor(colors.HexColor("#fbf8f0"))
        pdf.roundRect(x, panel_y, panel_width, panel_height, 3, fill=1, stroke=1)

        image_height = panel_height * 0.62
        image_y = panel_y + panel_height - image_height
        image_path = _panel_image_path(str(panel.get("image_url") or ""), base_dir)
        if image_path:
            try:
                pdf.drawImage(
                    ImageReader(str(image_path)),
                    x + 1,
                    image_y + 1,
                    width=panel_width - 2,
                    height=image_height - 2,
                    preserveAspectRatio=True,
                    anchor="c",
                    mask="auto",
                )
            except Exception:
                _draw_fallback_art(pdf, x + 1, image_y + 1, panel_width - 2, image_height - 2, index)
        else:
            _draw_fallback_art(pdf, x + 1, image_y + 1, panel_width - 2, image_height - 2, index)

        pdf.setFillColor(colors.HexColor("#fbf8f0"))
        pdf.setStrokeColor(colors.HexColor("#22221e"))
        bubble_x = x + panel_width * 0.08
        bubble_y = image_y + image_height * 0.76
        pdf.roundRect(bubble_x, bubble_y, panel_width * 0.82, 28, 12, fill=1, stroke=1)
        _draw_wrapped_text(
            pdf,
            str(panel.get("dialogue") or "..."),
            bubble_x + 7,
            bubble_y + 17,
            panel_width * 0.68,
            font="Helvetica-Oblique",
            size=7,
            leading=8,
            max_lines=2,
        )

        text_y = image_y - 16
        pdf.setFillColor(colors.HexColor("#e65345"))
        pdf.setFont("Courier-Bold", 7)
        pdf.drawString(x + 8, text_y, f"PANEL {index + 1:02d} / {str(panel.get('scene') or 'STORY BEAT').upper()[:26]}")
        text_y -= 14
        pdf.setFillColor(colors.HexColor("#22221e"))
        text_y = _draw_wrapped_text(
            pdf,
            str(panel.get("visual") or panel.get("caption") or ""),
            x + 8,
            text_y,
            panel_width - 16,
            font="Helvetica",
            size=8,
            leading=10,
            max_lines=4,
        )
        text_y -= 3
        _draw_wrapped_text(
            pdf,
            f"Caption: {panel.get('caption') or ''}",
            x + 8,
            text_y,
            panel_width - 16,
            font="Helvetica-Oblique",
            size=7,
            leading=9,
            max_lines=2,
        )

    pdf.setFillColor(colors.HexColor("#5c5a52"))
    pdf.setFont("Courier", 7)
    pdf.drawString(margin, 12, "ComicCraft / a page-sized thought experiment")
    pdf.drawRightString(page_width - margin, 12, "Generated panels and story text")
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()