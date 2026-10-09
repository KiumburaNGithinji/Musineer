"""BPM + musical key detection.

Tempo comes from librosa's beat tracker. Key is estimated by correlating the
track's average chroma vector against the Krumhansl-Schmuckler major/minor
key profiles and picking the best-fitting rotation — a standard, lightweight
approach that doesn't need a trained model.
"""

from pathlib import Path

import librosa
import numpy as np

from .converter import ConversionError, download_youtube_audio

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# Krumhansl-Schmuckler key profiles.
_MAJOR_PROFILE = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_MINOR_PROFILE = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])

# Camelot wheel notation, keyed by "<note> major"/"<note> minor".
_CAMELOT = {
    "C major": "8B", "A minor": "8A",
    "G major": "9B", "E minor": "9A",
    "D major": "10B", "B minor": "10A",
    "A major": "11B", "F# minor": "11A",
    "E major": "12B", "C# minor": "12A",
    "B major": "1B", "G# minor": "1A",
    "F# major": "2B", "D# minor": "2A",
    "C# major": "3B", "A# minor": "3A",
    "G# major": "4B", "F minor": "4A",
    "D# major": "5B", "C minor": "5A",
    "A# major": "6B", "G minor": "6A",
    "F major": "7B", "D minor": "7A",
}


def analyze_youtube_audio(url: str) -> dict:
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        source_path, info = download_youtube_audio(url, Path(tmpdir))
        result = analyze_file(source_path)
        result["title"] = info.get("title")
        return result


def analyze_uploaded_file(source_path: Path) -> dict:
    return analyze_file(Path(source_path))


MAX_ANALYSIS_SECONDS = 90


def analyze_file(path: Path) -> dict:
    try:
        y, sr = librosa.load(str(path), mono=True, sr=22050, duration=MAX_ANALYSIS_SECONDS)
    except Exception as e:
        raise ConversionError(f"Could not read audio for analysis: {e}") from e

    if y.size == 0:
        raise ConversionError("Audio file appears to be empty")

    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
    bpm = float(np.atleast_1d(tempo)[0])

    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
    chroma_mean = chroma.mean(axis=1)
    key, scale, confidence = _estimate_key(chroma_mean)
    key_label = f"{key} {scale}"

    return {
        "bpm": round(bpm, 1),
        "key": key_label,
        "camelot": _CAMELOT.get(key_label),
        "confidence": round(confidence, 2),
    }


def _estimate_key(chroma_mean: np.ndarray) -> tuple[str, str, float]:
    best_score = -np.inf
    best_note, best_scale = "C", "major"

    for i in range(12):
        major_score = _correlate(chroma_mean, np.roll(_MAJOR_PROFILE, i))
        minor_score = _correlate(chroma_mean, np.roll(_MINOR_PROFILE, i))
        if major_score > best_score:
            best_score, best_note, best_scale = major_score, NOTE_NAMES[i], "major"
        if minor_score > best_score:
            best_score, best_note, best_scale = minor_score, NOTE_NAMES[i], "minor"

    return best_note, best_scale, best_score


def _correlate(a: np.ndarray, b: np.ndarray) -> float:
    a = a - a.mean()
    b = b - b.mean()
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    return float(np.dot(a, b) / denom) if denom else 0.0
