from pathlib import Path
from typing import Annotated
import base64
import logging

from fastapi import Body, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ai import GeminiError, generate_ai_comic, gemini_configured
from pdf_export import build_comic_pdf


BASE_DIR = Path(__file__).resolve().parent
GENERATED_DIR = BASE_DIR / "static" / "generated"
logger = logging.getLogger("comiccraft")

app = FastAPI(
    title="ComicCraft AI App",
    description="An AI comic story creator with Gemini support and a deterministic demo fallback.",
)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")

GENRE_LABELS = {
    "superhero": "Superhero",
    "mystery": "Mystery",
    "slice-of-life": "Slice of life",
    "fantasy": "Fantasy",
}

STYLE_LABELS = {
    "ink-and-wash": "ink and wash",
    "risograph": "risograph poster",
    "scratchboard": "scratchboard noir",
}


def wants_json(request: Request) -> bool:
    return "application/json" in request.headers.get("accept", "")


def demo_panel_image(index: int, visual_style: str, palette: str) -> str:
    """A small inline image so DEMO_MODE still has real panel artwork."""
    palette_colors = {
        "signal-red": ("#8ab7b0", "#e65345", "#f2ca68"),
        "sea-glass": ("#8ab7b0", "#d9efe6", "#5c8b86"),
        "night-bus": ("#292a42", "#6f77b8", "#f2ca68"),
    }
    colors = palette_colors.get(palette, palette_colors["signal-red"])
    accent = colors[index % len(colors)]
    secondary = colors[(index + 1) % len(colors)]
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 860">
      <rect width="640" height="860" fill="{colors[0]}"/>
      <path d="M0 560 Q 210 {470 + index * 24} 640 555 V860 H0Z" fill="{secondary}"/>
      <circle cx="{170 + index * 72}" cy="{220 + index * 42}" r="{76 + index * 9}" fill="{accent}" stroke="#22221e" stroke-width="9"/>
      <path d="M300 820 L390 425 L500 820Z" fill="#22221e"/>
      <circle cx="465" cy="145" r="20" fill="#22221e"/>
      <circle cx="520" cy="190" r="10" fill="#22221e"/>
      <path d="M90 120 L230 95 M88 155 L198 138" stroke="#22221e" stroke-width="10" stroke-linecap="round"/>
    </svg>"""
    encoded = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


def build_demo_comic(
    prompt: str,
    genre: str,
    visual_style: str = "ink-and-wash",
    palette: str = "signal-red",
) -> dict:
    """Turn a prompt into a predictable demo result without calling an API."""
    clean_prompt = " ".join(prompt.split())
    subject = clean_prompt.rstrip(".!?") or "A new idea"
    genre_label = GENRE_LABELS.get(genre, "Adventure")

    panels = [
        {
            "number": "01",
            "scene": "Establishing shot",
            "visual": f"Wide frame: {subject} enters a world that feels bigger than expected.",
            "dialogue": "Every story starts with one impossible decision.",
            "caption": "THE FIRST BEAT",
            "tone": "setup",
        },
        {
            "number": "02",
            "scene": "The turn",
            "visual": f"Close-up: a surprising clue changes what {subject.lower()} thought was true.",
            "dialogue": "Wait. That was never part of the plan.",
            "caption": "SOMETHING SHIFTS",
            "tone": "turn",
        },
        {
            "number": "03",
            "scene": "Forward motion",
            "visual": "The frame opens up again. The next page is ready to be drawn.",
            "dialogue": "Then let's make the next move count.",
            "caption": "TO BE CONTINUED",
            "tone": "cliffhanger",
        },
    ]
    for index, panel in enumerate(panels):
        panel["image_url"] = demo_panel_image(index, visual_style, palette)
        panel["image_alt"] = f"Demo comic panel {index + 1}: {panel['scene']}"

    return {
        "title": f"{subject[:42]}{'…' if len(subject) > 42 else ''}",
        "genre": genre_label,
        "style": STYLE_LABELS.get(visual_style, "ink and wash"),
        "palette": palette,
        "status": "concept ready",
        "generation_mode": "DEMO_MODE",
        "provider": "Local fallback",
        "character_bible": "A recurring protagonist with a bold silhouette and one memorable prop.",
        "style_bible": f"{STYLE_LABELS.get(visual_style, 'ink and wash')} linework in a {palette} limited palette.",
        "panels": panels,
    }


def page_context(
    request: Request,
    *,
    prompt: str = "",
    genre: str = "superhero",
    comic: dict | None = None,
    error: str | None = None,
) -> dict:
    return {
        "request": request,
        "prompt": prompt,
        "prompt_value": prompt,
        "genre": genre,
        "genres": GENRE_LABELS,
        "comic": comic,
        "error": error,
        "demo_mode": not gemini_configured(),
        "ai_available": gemini_configured(),
    }


@app.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context=page_context(request),
    )


@app.post("/generate", response_class=HTMLResponse)
async def generate(
    request: Request,
    prompt: Annotated[str, Form()] = "",
    genre: Annotated[str, Form()] = "superhero",
    visual_style: Annotated[str, Form()] = "ink-and-wash",
    palette: Annotated[str, Form()] = "signal-red",
) -> HTMLResponse:
    prompt = prompt.strip()
    if not prompt:
        message = "Give your comic a starting idea before generating."
        if wants_json(request):
            return JSONResponse({"error": message}, status_code=400)
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context=page_context(
                request,
                prompt=prompt,
                genre=genre,
                error=message,
            ),
            status_code=400,
        )

    if len(prompt) < 10:
        message = "Give the page one clear beat — at least a sentence fragment."
        if wants_json(request):
            return JSONResponse({"error": message}, status_code=400)
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context=page_context(
                request,
                prompt=prompt,
                genre=genre,
                error=message,
            ),
            status_code=400,
        )

    if len(prompt) > 280:
        message = "Keep the starting idea under 280 characters for this demo."
        if wants_json(request):
            return JSONResponse({"error": message}, status_code=400)
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context=page_context(
                request,
                prompt=prompt,
                genre=genre,
                error=message,
            ),
            status_code=400,
        )

    notice = None
    if gemini_configured():
        try:
            comic = await generate_ai_comic(
                prompt,
                genre,
                visual_style,
                palette,
                GENERATED_DIR,
            )
        except GeminiError as exc:
            logger.warning("Gemini generation unavailable; using DEMO_MODE fallback: %s", exc)
            comic = build_demo_comic(prompt, genre, visual_style, palette)
            notice = "Gemini was unavailable, so ComicCraft used DEMO_MODE for this page."
    else:
        comic = build_demo_comic(prompt, genre, visual_style, palette)
        notice = "DEMO_MODE is active. Add GEMINI_API_KEY or GOOGLE_API_KEY to enable Gemini."
    if notice:
        comic["generation_notice"] = notice
    if wants_json(request):
        return JSONResponse({"result": comic})

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context=page_context(
            request,
            prompt=prompt,
            genre=genre,
            comic=comic,
        ),
    )


@app.post("/export/pdf")
async def export_pdf(payload: dict = Body(...)) -> Response:
    comic = payload.get("comic", payload)
    if not isinstance(comic, dict) or not comic.get("panels"):
        return JSONResponse({"error": "Generate a comic before exporting a PDF."}, status_code=400)
    pdf_bytes = build_comic_pdf(comic, BASE_DIR)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="comiccraft-comic.pdf"'},
    )


@app.get("/health", response_class=JSONResponse)
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "ComicCraft"})