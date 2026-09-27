# ComicCraft AI App

An AI comic story creator that turns a short story idea into a three-panel comic preview, with Gemini text/image generation when configured and a deterministic local fallback when it is not.

## Run & Operate

- `pnpm --filter @workspace/comiccraft-ai-app run dev` — run the ComicCraft app
- `pnpm run typecheck` — full typecheck across all packages
- `pnpm run build` — typecheck + build all packages
- `uv run --project ../.. uvicorn app:app --reload` — run the FastAPI app directly from `artifacts/comiccraft-ai-app`

## Stack

- Python 3.13, FastAPI, Uvicorn, Jinja2, ReportLab
- HTML form frontend with template-rendered CSS
- Optional Gemini REST integration using environment variables/secrets; no API key is required for DEMO_MODE

## Where things live

- `artifacts/comiccraft-ai-app/app.py` — FastAPI routes, demo fallback, and PDF route
- `artifacts/comiccraft-ai-app/ai.py` — optional Gemini outline/dialogue/image generation and prompt continuity
- `artifacts/comiccraft-ai-app/pdf_export.py` — comic PDF composition
- `artifacts/comiccraft-ai-app/templates/index.html` — Jinja2 page template
- `artifacts/comiccraft-ai-app/static/styles.css` — app styling

## Architecture decisions

- The first version uses server-rendered Jinja2 instead of a client framework to keep the core flow small and easy to extend.
- Demo generation remains deterministic and local so the app is usable without credentials or external services.
- If `GEMINI_API_KEY` or `GOOGLE_API_KEY` is present, ComicCraft requests a structured outline from Gemini and generates one image per panel using shared character/style prompt bibles.
- The Gemini base URL and models can be overridden with `GEMINI_API_BASE_URL`, `GEMINI_TEXT_MODEL`, and `GEMINI_IMAGE_MODEL`.

## Product

Users enter a comic idea, choose a genre/style/palette, and receive a three-panel preview with scene direction, dialogue, captions, panel artwork, and PDF export.

## User preferences

_Populate as you build — explicit user instructions worth remembering across sessions._

## Gotchas

_Populate as you build — sharp edges, "always run X before Y" rules._

## Pointers

- See the `pnpm-workspace` skill for workspace structure, TypeScript setup, and package details
