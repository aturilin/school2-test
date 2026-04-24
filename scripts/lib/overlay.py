"""PNG overlay per SPEC.md contract. Renders title onto a template.

Contract (from thumbnails/*/SPEC.md):
- Font: HelveticaNeue.ttc index 1 (Bold), white #FFFFFF, shadow #000000 offset (3, 5).
- Start size 128px, step -2px, min 44px, max 3 lines.
- Title left-anchored in 5%..60% width band, vertically centered.
- 12 <= len(title) <= 55. No '!', '?', '…' at end; no emoji; no ALL-CAPS tokens > 3 chars.
- On failure: raise, don't truncate or try to fit blindly.
"""

from __future__ import annotations

import re
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

FONT_PATH = "/System/Library/Fonts/HelveticaNeue.ttc"
FONT_INDEX = 1  # Bold
FILL = (255, 255, 255)
SHADOW = (0, 0, 0)
SHADOW_OFFSET = (3, 5)

TEXT_LEFT_PCT = 0.05
TEXT_RIGHT_PCT = 0.60

START_SIZE = 128
MIN_SIZE = 44
STEP = 2
MAX_LINES = 3

_EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E0-\U0001F1FF]"
)
_CAPS_RE = re.compile(r"[А-ЯA-Z]{4,}")


class TitleError(ValueError):
    pass


def validate_title(title: str) -> None:
    n = len(title)
    if n < 12:
        raise TitleError(f"title too short ({n} < 12)")
    if n > 55:
        raise TitleError(f"title too long ({n} > 55)")
    if title.rstrip().endswith(("!", "?", "…", ".")):
        raise TitleError("title must not end with !, ?, …, .")
    if _EMOJI_RE.search(title):
        raise TitleError("emoji not allowed")
    for tok in _CAPS_RE.findall(title):
        raise TitleError(f"ALL CAPS token not allowed: {tok!r}")


def _wrap(text: str, font: ImageFont.FreeTypeFont, max_w: int) -> list[str] | None:
    """Greedy word-wrap. Returns None if any single word is wider than max_w."""
    words = text.split()
    lines: list[str] = []
    cur: list[str] = []
    for w in words:
        trial = (" ".join(cur + [w])).strip()
        tw = font.getlength(trial)
        if tw <= max_w:
            cur.append(w)
        else:
            if not cur:
                if font.getlength(w) > max_w:
                    return None
                lines.append(w)
                cur = []
            else:
                lines.append(" ".join(cur))
                if font.getlength(w) > max_w:
                    return None
                cur = [w]
    if cur:
        lines.append(" ".join(cur))
    return lines


def _pick_size_and_lines(title: str, max_w: int) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    for size in range(START_SIZE, MIN_SIZE - 1, -STEP):
        font = ImageFont.truetype(FONT_PATH, size=size, index=FONT_INDEX)
        lines = _wrap(title, font, max_w)
        if lines is None:
            continue
        if len(lines) <= MAX_LINES:
            return font, lines
    raise TitleError(
        f"cannot fit title in {MAX_LINES} lines between {MIN_SIZE}-{START_SIZE}px"
    )


def render(template_path: str | Path, title: str, out_path: str | Path) -> Path:
    """Render title onto template and save. Returns output path."""
    validate_title(title)
    bg = Image.open(template_path).convert("RGBA")
    canvas_w, canvas_h = bg.size

    left = int(canvas_w * TEXT_LEFT_PCT)
    right = int(canvas_w * TEXT_RIGHT_PCT)
    max_w = right - left

    font, lines = _pick_size_and_lines(title, max_w)

    ascent, descent = font.getmetrics()
    line_h = ascent + descent
    block_h = line_h * len(lines)
    top = (canvas_h - block_h) // 2

    draw = ImageDraw.Draw(bg)
    y = top
    for line in lines:
        draw.text(
            (left + SHADOW_OFFSET[0], y + SHADOW_OFFSET[1]),
            line,
            font=font,
            fill=SHADOW,
        )
        draw.text((left, y), line, font=font, fill=FILL)
        y += line_h

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    bg.convert("RGB").save(out_path, "PNG")
    return out_path


if __name__ == "__main__":
    # smoke test
    import sys

    if len(sys.argv) < 4:
        print("usage: overlay.py <template.png> <title> <out.png>")
        sys.exit(1)
    p = render(sys.argv[1], sys.argv[2], sys.argv[3])
    print(f"wrote {p}")
