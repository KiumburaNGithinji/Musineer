"""Core conversion logic: YouTube URL -> local MP3/WAV file(s).

Kept independent of the web layer so it can be reused as-is by a CLI
or a desktop shell (e.g. pywebview) later without changes.
"""

import re
import subprocess
import tempfile
from pathlib import Path
from typing import Iterable

import yt_dlp

SUPPORTED_FORMATS = {"mp3", "wav"}


class ConversionError(Exception):
    """Raised when a YouTube URL can't be downloaded or converted."""


def download_youtube_audio(url: str, dest_dir: Path) -> tuple[Path, dict]:
    """Download the best available audio for a YouTube URL into dest_dir.

    Returns (path to downloaded source file, yt-dlp info dict).
    """
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": str(Path(dest_dir) / "%(id)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            downloaded_path = Path(ydl.prepare_filename(info))
    except yt_dlp.utils.DownloadError as e:
        raise ConversionError(f"Could not download audio: {e}") from e

    if not downloaded_path.exists():
        raise ConversionError("Download succeeded but source file was not found")

    return downloaded_path, info


def convert_youtube_audio(url: str, formats: Iterable[str], output_dir: Path) -> dict:
    formats = list(formats)
    unsupported = set(formats) - SUPPORTED_FORMATS
    if unsupported:
        raise ConversionError(f"Unsupported format(s): {', '.join(sorted(unsupported))}")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmpdir:
        downloaded_path, info = download_youtube_audio(url, Path(tmpdir))

        title = sanitize_filename(info.get("title") or info.get("id") or "audio")
        files = {}
        for fmt in formats:
            dest = unique_path(output_dir / f"{title}.{fmt}")
            run_ffmpeg(downloaded_path, dest, fmt)
            files[fmt] = dest.name

        return {
            "title": info.get("title"),
            "duration": info.get("duration"),
            "uploader": info.get("uploader"),
            "files": files,
        }


def sanitize_filename(name: str) -> str:
    name = re.sub(r'[\\/*?:"<>|]', "", name).strip().strip(".")
    return name or "audio"


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    i = 1
    while True:
        candidate = path.with_name(f"{stem} ({i}){suffix}")
        if not candidate.exists():
            return candidate
        i += 1


def run_ffmpeg(source: Path, dest: Path, fmt: str) -> None:
    if fmt == "mp3":
        codec_args = ["-c:a", "libmp3lame", "-b:a", "320k"]
    else:  # wav
        codec_args = ["-c:a", "pcm_s16le", "-ar", "44100", "-ac", "2"]

    cmd = ["ffmpeg", "-y", "-i", str(source), *codec_args, str(dest)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise ConversionError(f"ffmpeg failed converting to {fmt}: {result.stderr[-500:]}")
