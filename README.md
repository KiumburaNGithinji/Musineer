# Musineer

A personal toolkit for music production workflows. First tool: convert a YouTube
link's audio into MP3/WAV files ready to drop into FL Studio.

More tools will be added as separate features under the same app over time.

## Setup

```bash
cd Musineer
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Requires `ffmpeg` on your PATH (`brew install ffmpeg` on macOS).

## Run

```bash
uvicorn backend.main:app --reload
```

Open http://127.0.0.1:8000, paste a YouTube link, pick MP3/WAV, convert.
Converted files land in `downloads/` (gitignored) and are also downloadable
from the browser.

## Notes

- Only use this on content you have the right to download (your own uploads,
  royalty-free/Creative Commons tracks, reference audio for personal
  production, etc.) — downloading copyrighted YouTube audio can violate
  YouTube's Terms of Service.
- The backend (`backend/converter.py`) is UI-agnostic on purpose: the plan is
  to eventually wrap this same FastAPI backend in a desktop shell (e.g.
  pywebview or a PyInstaller-packaged app) once it's proven useful as a web
  app, without rewriting the conversion logic.
