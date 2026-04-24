"""Transcript loader. Uses pre-made text file if present, else local Whisper.

Local Whisper: `openai-whisper` (pip). First call downloads the model.
Model: "small" — 500MB, fast enough on Apple Silicon, good on Russian.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

TRANSCRIPTS_DIR = Path(__file__).resolve().parents[2] / "inputs" / "transcripts"
VIDEOS_DIR = Path(__file__).resolve().parents[2] / "inputs" / "videos"

_WHISPER_MODEL = None


def _extract_audio(video_path: Path) -> Path:
    """Extract 16kHz mono wav for Whisper."""
    out = Path(tempfile.mkstemp(suffix=".wav")[1])
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", str(video_path),
            "-vn", "-ac", "1", "-ar", "16000",
            str(out),
        ],
        check=True,
    )
    return out


def _whisper(audio_path: Path) -> str:
    global _WHISPER_MODEL
    import whisper  # openai-whisper package, runs locally

    if _WHISPER_MODEL is None:
        _WHISPER_MODEL = whisper.load_model("small")
    result = _WHISPER_MODEL.transcribe(str(audio_path), language="ru", fp16=False)
    return result["text"]


def get_transcript(video_filename: str) -> str:
    """Return transcript for a video. Cached on disk in inputs/transcripts/."""
    stem = Path(video_filename).stem
    txt_path = TRANSCRIPTS_DIR / f"{stem}.txt"
    if txt_path.exists():
        return txt_path.read_text(encoding="utf-8").strip()

    video_path = VIDEOS_DIR / video_filename
    if not video_path.exists():
        raise FileNotFoundError(video_path)

    audio = _extract_audio(video_path)
    try:
        text = _whisper(audio).strip()
    finally:
        try:
            audio.unlink()
        except OSError:
            pass

    TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    txt_path.write_text(text + "\n", encoding="utf-8")
    return text


if __name__ == "__main__":
    import sys

    name = sys.argv[1] if len(sys.argv) > 1 else "clip_061e39.mp4"
    t = get_transcript(name)
    print(f"[{name}] {len(t)} chars\n---\n{t[:500]}...")
