"""Vocal / instrumental separation via Demucs.

Runs Demucs in --two-stems=vocals mode, which is faster and lighter than
full 4-stem separation since it only needs to isolate vocals vs. everything
else. Reuses converter.py's filename/ffmpeg helpers to produce MP3/WAV
outputs from Demucs's WAV stems.
"""

import subprocess
import tempfile
from pathlib import Path
from typing import Iterable

from .converter import ConversionError, download_youtube_audio, run_ffmpeg, sanitize_filename, unique_path

SUPPORTED_STEMS = {"vocals", "instrumental"}
SUPPORTED_FORMATS = {"mp3", "wav"}

# Demucs's --two-stems=vocals mode names the accompaniment stem "no_vocals".
_DEMUCS_STEM_FILENAME = {"vocals": "vocals", "instrumental": "no_vocals"}
_MODEL_NAME = "htdemucs"


def separate_youtube_audio(url: str, stems: Iterable[str], formats: Iterable[str], output_dir: Path) -> dict:
    with tempfile.TemporaryDirectory() as tmpdir:
        source_path, info = download_youtube_audio(url, Path(tmpdir))
        title = sanitize_filename(info.get("title") or info.get("id") or "audio")
        files = _separate(source_path, title, stems, formats, output_dir)
        return {
            "title": info.get("title"),
            "duration": info.get("duration"),
            "uploader": info.get("uploader"),
            "files": files,
        }


def separate_uploaded_file(source_path: Path, original_name: str, stems: Iterable[str], formats: Iterable[str], output_dir: Path) -> dict:
    title = sanitize_filename(Path(original_name).stem or "audio")
    files = _separate(Path(source_path), title, stems, formats, output_dir)
    return {"title": title, "files": files}


def _separate(source_path: Path, title: str, stems: Iterable[str], formats: Iterable[str], output_dir: Path) -> dict:
    stems = list(stems)
    formats = list(formats)
    unsupported_stems = set(stems) - SUPPORTED_STEMS
    if unsupported_stems:
        raise ConversionError(f"Unsupported stem(s): {', '.join(sorted(unsupported_stems))}")
    unsupported_formats = set(formats) - SUPPORTED_FORMATS
    if unsupported_formats:
        raise ConversionError(f"Unsupported format(s): {', '.join(sorted(unsupported_formats))}")
    if not stems:
        raise ConversionError("Pick at least one of: vocals, instrumental")
    if not formats:
        raise ConversionError("Pick at least one of: mp3, wav")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as demucs_out:
        cmd = [
            "demucs",
            "--two-stems", "vocals",
            "-n", _MODEL_NAME,
            "-o", demucs_out,
            str(source_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise ConversionError(f"Stem separation failed: {result.stderr[-800:]}")

        track_dir = Path(demucs_out) / _MODEL_NAME / source_path.stem
        files = {}
        for stem in stems:
            stem_wav = track_dir / f"{_DEMUCS_STEM_FILENAME[stem]}.wav"
            if not stem_wav.exists():
                raise ConversionError(f"Expected Demucs output not found: {stem_wav.name}")
            # Convert non-wav formats first, then move the wav last —
            # moving it earlier would remove the ffmpeg source file.
            for fmt in sorted(formats, key=lambda f: f == "wav"):
                dest = unique_path(output_dir / f"{title} ({stem}).{fmt}")
                if fmt == "wav":
                    stem_wav.replace(dest)
                else:
                    run_ffmpeg(stem_wav, dest, fmt)
                files[f"{stem}_{fmt}"] = dest.name

        return files
