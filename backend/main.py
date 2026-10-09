import re
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, field_validator

from .analyze import analyze_uploaded_file, analyze_youtube_audio
from .converter import SUPPORTED_FORMATS, ConversionError, convert_youtube_audio
from .stems import SUPPORTED_STEMS, separate_uploaded_file, separate_youtube_audio

BASE_DIR = Path(__file__).resolve().parent.parent
DOWNLOADS_DIR = BASE_DIR / "downloads"
FRONTEND_DIR = BASE_DIR / "frontend"
DOWNLOADS_DIR.mkdir(exist_ok=True)

YOUTUBE_URL_RE = re.compile(
    r"^https?://(www\.|music\.)?(youtube\.com|youtu\.be)/", re.IGNORECASE
)

ALLOWED_UPLOAD_EXTENSIONS = {".mp3", ".wav", ".m4a", ".flac", ".ogg", ".aac"}
MAX_UPLOAD_BYTES = 200 * 1024 * 1024  # 200 MB

app = FastAPI(title="Musineer Converter")


class ConvertRequest(BaseModel):
    url: str
    formats: list[str]

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        if not YOUTUBE_URL_RE.match(v.strip()):
            raise ValueError("Only YouTube URLs are supported")
        return v.strip()

    @field_validator("formats")
    @classmethod
    def validate_formats(cls, v: list[str]) -> list[str]:
        if not v or not set(v).issubset(SUPPORTED_FORMATS):
            raise ValueError(f"formats must be a non-empty subset of {sorted(SUPPORTED_FORMATS)}")
        return v


@app.post("/api/convert")
def convert(req: ConvertRequest):
    try:
        return convert_youtube_audio(req.url, req.formats, DOWNLOADS_DIR)
    except ConversionError as e:
        raise HTTPException(status_code=400, detail=str(e))


class ExtractRequest(BaseModel):
    url: str
    stems: list[str]
    formats: list[str]

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        if not YOUTUBE_URL_RE.match(v.strip()):
            raise ValueError("Only YouTube URLs are supported")
        return v.strip()

    @field_validator("stems")
    @classmethod
    def validate_stems(cls, v: list[str]) -> list[str]:
        if not v or not set(v).issubset(SUPPORTED_STEMS):
            raise ValueError(f"stems must be a non-empty subset of {sorted(SUPPORTED_STEMS)}")
        return v

    @field_validator("formats")
    @classmethod
    def validate_formats(cls, v: list[str]) -> list[str]:
        if not v or not set(v).issubset(SUPPORTED_FORMATS):
            raise ValueError(f"formats must be a non-empty subset of {sorted(SUPPORTED_FORMATS)}")
        return v


@app.post("/api/extract")
def extract(req: ExtractRequest):
    try:
        return separate_youtube_audio(req.url, req.stems, req.formats, DOWNLOADS_DIR)
    except ConversionError as e:
        raise HTTPException(status_code=400, detail=str(e))


def _validated_extension(filename: str | None) -> str:
    ext = Path(filename or "").suffix.lower()
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext or 'unknown'}")
    return ext


async def _save_upload_to_temp(file: UploadFile, tmp_path: Path) -> None:
    size = 0
    with tmp_path.open("wb") as out:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                raise HTTPException(status_code=400, detail="File too large (max 200MB)")
            out.write(chunk)


@app.post("/api/extract/upload")
async def extract_upload(
    file: UploadFile = File(...),
    stems: str = Form(...),
    formats: str = Form(...),
):
    stem_list = [s.strip() for s in stems.split(",") if s.strip()]
    format_list = [f.strip() for f in formats.split(",") if f.strip()]
    if not stem_list or not set(stem_list).issubset(SUPPORTED_STEMS):
        raise HTTPException(status_code=400, detail=f"stems must be a non-empty subset of {sorted(SUPPORTED_STEMS)}")
    if not format_list or not set(format_list).issubset(SUPPORTED_FORMATS):
        raise HTTPException(status_code=400, detail=f"formats must be a non-empty subset of {sorted(SUPPORTED_FORMATS)}")

    ext = _validated_extension(file.filename)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir) / f"upload{ext}"
        await _save_upload_to_temp(file, tmp_path)
        try:
            return separate_uploaded_file(tmp_path, file.filename or "audio", stem_list, format_list, DOWNLOADS_DIR)
        except ConversionError as e:
            raise HTTPException(status_code=400, detail=str(e))


class AnalyzeRequest(BaseModel):
    url: str

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        if not YOUTUBE_URL_RE.match(v.strip()):
            raise ValueError("Only YouTube URLs are supported")
        return v.strip()


@app.post("/api/analyze")
def analyze(req: AnalyzeRequest):
    try:
        return analyze_youtube_audio(req.url)
    except ConversionError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/analyze/upload")
async def analyze_upload(file: UploadFile = File(...)):
    ext = _validated_extension(file.filename)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir) / f"upload{ext}"
        await _save_upload_to_temp(file, tmp_path)
        try:
            result = analyze_uploaded_file(tmp_path)
        except ConversionError as e:
            raise HTTPException(status_code=400, detail=str(e))
        result["title"] = Path(file.filename or "audio").stem
        return result


@app.get("/api/download/{filename}")
def download(filename: str):
    safe_name = Path(filename).name  # strip any path components
    file_path = DOWNLOADS_DIR / safe_name
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path, filename=safe_name)


app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
