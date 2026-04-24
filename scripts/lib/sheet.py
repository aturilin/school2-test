"""Google Sheet I/O for v5 schema: 3 rows per video, 2 checkboxes per row.

Title and preview are inseparable (title burned into PNG) → one checkbox
"pick_title" picks both. Description is picked independently.

Schema:
  A  row_num
  B  video_filename
  C  subject
  D  variant                1/2/3
  E  preview                =IMAGE
  F  title
  G  pick_title             checkbox (picks title + preview together)
  H  description
  I  pick_desc              checkbox
  J  title_override         if set → preview rerendered on publish
  K  description_override
  L  vh_video_id
  M  published_at
  N  thumb_local            hidden
"""

from __future__ import annotations

import json
import os
import subprocess
from typing import Optional

COLUMNS = [
    "row_num", "video_filename", "subject", "variant",
    "preview", "title", "pick_title",
    "description", "pick_desc",
    "title_override", "description_override",
    "vh_video_id", "published_at", "thumb_local",
]
SHEET_TAB = "videos"
RANGE_ALL = f"{SHEET_TAB}!A1:N"

VH_COL_LETTER = "L"


def _gws(args: list[str], payload: Optional[dict] = None) -> dict:
    cmd = ["gws"] + args
    if payload is not None:
        cmd += ["--json", json.dumps(payload, ensure_ascii=False)]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if res.returncode != 0:
        raise RuntimeError(f"gws failed: {res.stderr}\n{res.stdout}")
    return json.loads(res.stdout) if res.stdout.strip() else {}


def _sheet_id() -> str:
    sid = os.environ.get("SHEET_ID")
    if not sid:
        raise RuntimeError("SHEET_ID not in env")
    return sid


def _normalize_bool(v) -> bool:
    if isinstance(v, bool):
        return v
    return str(v).strip().upper() == "TRUE"


def read_all() -> list[dict]:
    sid = _sheet_id()
    data = _gws([
        "sheets", "spreadsheets", "values", "get",
        "--params", json.dumps({
            "spreadsheetId": sid,
            "range": RANGE_ALL,
            "valueRenderOption": "UNFORMATTED_VALUE",
        }),
    ])
    rows = data.get("values") or []
    if not rows:
        return []
    out: list[dict] = []
    for r in rows[1:]:
        padded = list(r) + [""] * (len(COLUMNS) - len(r))
        d = dict(zip(COLUMNS, padded[:len(COLUMNS)]))
        d["pick_title"] = _normalize_bool(d.get("pick_title"))
        d["pick_desc"] = _normalize_bool(d.get("pick_desc"))
        out.append(d)
    return out


def list_present_videos() -> set[str]:
    return {r["video_filename"] for r in read_all() if r.get("video_filename")}


def update_published(row_index: int, video_id: str, published_at: str) -> None:
    """Write vh_video_id + published_at on cols L:M.

    row_index is 0-based among data rows (sheet row number = row_index + 2).
    """
    sheet_row = row_index + 2
    sid = _sheet_id()
    _gws([
        "sheets", "spreadsheets", "values", "update",
        "--params", json.dumps({
            "spreadsheetId": sid,
            "range": f"{SHEET_TAB}!{VH_COL_LETTER}{sheet_row}:M{sheet_row}",
            "valueInputOption": "USER_ENTERED",
        }),
    ], payload={"values": [[video_id, published_at]]})
