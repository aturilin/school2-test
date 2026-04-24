"""Deterministic CLI used by the two skills. No LLM calls — Claude (the agent
running the skill) does the thinking and calls these for mechanical steps.

Subcommands:
  list-pending                  → video filenames not yet in Sheet, one per line
  transcript <video_filename>   → prints transcript text (cached to disk)
  render <subject> <title> <out_basename>
                                → renders PNG on template, prints absolute path
  ensure-header                 → writes Sheet header row if missing
  append-row <json>             → appends row dict (JSON string) to Sheet
  list-approved                 → JSON of rows ready to publish (approved,
                                  not yet published) with stable row indices
  mark-published <row_index> <video_id> <iso_timestamp>
                                → writes vh_video_id + published_at to Sheet
  upload <video_filename> <thumb_path> <title> <description>
                                → POST to video_hosting API, prints JSON response
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from lib import overlay, sheet, transcript  # noqa: E402

VIDEOS_DIR = ROOT / "inputs" / "videos"
THUMBS_DIR = ROOT / "inputs" / "thumbnails"
OUT_DIR = ROOT / "out" / "thumbnails"


def _load_env() -> None:
    load_dotenv(ROOT / ".env")


def cmd_list_pending() -> int:
    _load_env()
    existing = sheet.list_present_videos()
    for name in sorted(p.name for p in VIDEOS_DIR.glob("*.mp4")):
        if name not in existing:
            print(name)
    return 0


def cmd_transcript(video_filename: str) -> int:
    _load_env()
    text = transcript.get_transcript(video_filename)
    sys.stdout.write(text)
    return 0


def cmd_render(subject: str, title: str, out_basename: str) -> int:
    template = THUMBS_DIR / subject / "template.png"
    if not template.exists():
        raise SystemExit(f"no template for subject: {subject}")
    out_path = OUT_DIR / out_basename
    p = overlay.render(template, title, out_path)
    print(p.resolve())
    return 0


def _truthy(v) -> bool:
    if isinstance(v, bool):
        return v
    return str(v).strip().upper() in ("TRUE", "1", "YES", "✓", "X")


def cmd_list_approved() -> int:
    """Collect per-video combo from 2 checkboxes per row.

    For each video (3 rows):
      - one row with pick_title TRUE → provides title + thumbnail (they go
        together since title is burned into the PNG). title_override on
        that row, if set, triggers PNG re-render on publish.
      - one row with pick_desc TRUE → provides description (description_override wins).

    Video is ready iff both picks exist and vh_video_id is empty.
    If title_override is present on the picked row, publish-side will
    re-render the thumbnail with the overridden title.
    """
    _load_env()
    rows = sheet.read_all()
    published = {r["video_filename"] for r in rows if r.get("vh_video_id")}

    # Group row indices per video
    video_rows: dict[str, list[int]] = {}
    for i, r in enumerate(rows):
        name = r.get("video_filename")
        if not name or name in published:
            continue
        video_rows.setdefault(name, []).append(i)

    by_video: dict[str, dict] = {}
    for name, idxs in video_rows.items():
        slot = {"title_row": None, "desc_row": None}
        for i in idxs:
            r = rows[i]
            if r.get("pick_title"):
                if slot["title_row"] is not None:
                    print(f"  ! {name}: pick_title выбран в нескольких вариантах, беру первый", file=sys.stderr)
                    continue
                slot["title_row"] = i
            if r.get("pick_desc"):
                if slot["desc_row"] is not None:
                    print(f"  ! {name}: pick_desc выбран в нескольких вариантах, беру первый", file=sys.stderr)
                    continue
                slot["desc_row"] = i

        # Implicit pick via override: if no checkbox but exactly one row has
        # a non-empty override, treat that row as picked.
        if slot["title_row"] is None:
            overrides = [i for i in idxs if str(rows[i].get("title_override", "")).strip()]
            if len(overrides) == 1:
                slot["title_row"] = overrides[0]
                print(f"  · {name}: заголовок взят из override v{rows[overrides[0]]['variant']} (галка не нужна)", file=sys.stderr)
            elif len(overrides) > 1:
                print(f"  ! {name}: свой заголовок написан на {len(overrides)} строках — поставь галку в нужной", file=sys.stderr)
        if slot["desc_row"] is None:
            overrides = [i for i in idxs if str(rows[i].get("description_override", "")).strip()]
            if len(overrides) == 1:
                slot["desc_row"] = overrides[0]
                print(f"  · {name}: описание взято из override v{rows[overrides[0]]['variant']} (галка не нужна)", file=sys.stderr)
            elif len(overrides) > 1:
                print(f"  ! {name}: своё описание написано на {len(overrides)} строках — поставь галку", file=sys.stderr)

        by_video[name] = slot

    out = []
    for name, slot in by_video.items():
        missing = [k for k, v in slot.items() if v is None]
        if missing:
            print(f"  · {name}: ещё не полный комбо ({', '.join(missing)})", file=sys.stderr)
            continue
        title_row = rows[slot["title_row"]]
        desc_row = rows[slot["desc_row"]]
        override = str(title_row.get("title_override") or "").strip()
        title = override or str(title_row["title"]).strip()
        desc = str(desc_row.get("description_override") or desc_row["description"]).strip()
        thumb = str(title_row.get("thumb_local", "")).strip()

        # If editor rewrote the title, re-render the thumbnail so what gets
        # published matches what they typed.
        if override:
            subject = str(title_row.get("subject", "")).strip()
            template = THUMBS_DIR / subject / "template.png"
            stem = Path(name).stem
            override_out = OUT_DIR / f"{stem}_override.png"
            try:
                overlay.render(template, override, override_out)
                thumb = str(override_out.resolve())
            except overlay.TitleError as e:
                print(f"  ! {name}: override '{override}' не влезает — {e}; беру исходное превью", file=sys.stderr)

        out.append({
            "row_index": slot["title_row"],
            "video_filename": name,
            "chosen_title": title,
            "chosen_desc": desc,
            "chosen_thumb": thumb,
            "title_overridden": bool(override),
            "subject": title_row.get("subject"),
            "picks": {
                "title_variant": title_row.get("variant"),
                "desc_variant": desc_row.get("variant"),
            },
        })
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def cmd_mark_published(row_index: str, video_id: str, iso_ts: str) -> int:
    _load_env()
    sheet.update_published(int(row_index), video_id, iso_ts)
    print("ok")
    return 0


def cmd_upload(video_filename: str, thumb_path: str, title: str, description: str) -> int:
    _load_env()
    api_base = os.environ.get("VH_API_BASE", "http://localhost:5001/video_hosting/api")
    token = os.environ.get("VH_TOKEN")
    if not token:
        raise SystemExit("VH_TOKEN not in env")

    video_path = VIDEOS_DIR / video_filename
    if not video_path.exists():
        raise SystemExit(f"video not found: {video_path}")
    thumb = Path(thumb_path)
    if not thumb.exists():
        raise SystemExit(f"thumbnail not found: {thumb}")

    with video_path.open("rb") as vf, thumb.open("rb") as tf:
        resp = requests.post(
            f"{api_base}/videos",
            headers={"Authorization": f"Bearer {token}"},
            files={
                "video": (video_filename, vf, "video/mp4"),
                "thumbnail": (thumb.name, tf, "image/png"),
            },
            data={"title": title, "description": description},
            timeout=120,
        )
    if resp.status_code >= 400:
        raise SystemExit(f"upload failed: HTTP {resp.status_code} {resp.text}")
    print(resp.text)
    return 0


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    cmd, *rest = argv
    table = {
        "list-pending": cmd_list_pending,
        "transcript": cmd_transcript,
        "render": cmd_render,
        "list-approved": cmd_list_approved,
        "mark-published": cmd_mark_published,
        "upload": cmd_upload,
    }
    if cmd not in table:
        print(f"unknown command: {cmd}", file=sys.stderr)
        print(__doc__)
        return 2
    return table[cmd](*rest)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
