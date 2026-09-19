#!/usr/bin/env python3
"""Build similar-index.json + compressed thumbs from /workspace/surf-archive.

Discovers both layouts:
  Legacy:  /workspace/surf-archive/YYYY-MM-DD/<slug>/{notes.json,frame.jpg}
  Timed:   /workspace/surf-archive/YYYY-MM-DD/HHMM/<slug>/{notes.json,frame.jpg}
"""
from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime
from pathlib import Path

ARCHIVE_ROOT = Path("/workspace/surf-archive")
FORECAST_SLOTS = Path("/workspace/tide-data/forecast_slots.json")
REPO_ARCHIVE = Path("/workspace/surf-forecast-repo/archive")
INDEX_OUT = ARCHIVE_ROOT / "similar-index.json"
REPO_INDEX = REPO_ARCHIVE / "similar-index.json"

SLUG_TO_SPOT = {
    "zhongjiao": "中角",
    "wuwei": "無尾港",
    "zhunan": "竹南假日之森",
}
SPOT_TO_SLUG = {v: k for k, v in SLUG_TO_SPOT.items()}

DRIVE_FOLDER_TMPL = "https://drive.google.com/drive/folders/{fid}"
HHMM_RE = re.compile(r"^\d{4}$")
DATE_RE = re.compile(r"^20\d{2}-\d{2}-\d{2}$")


def _parse_captured_hour(captured_at: str | None) -> int | None:
    if not captured_at:
        return None
    m = re.search(r"T(\d{2}):", captured_at)
    if m:
        return int(m.group(1))
    return None


def _hhmm_from_captured(captured_at: str | None, fallback: str = "0000") -> str:
    """Derive HHMM from captured_at (e.g. 11:45 → 1145)."""
    if not captured_at:
        return fallback
    m = re.search(r"T(\d{2}):(\d{2})", captured_at)
    if m:
        return f"{m.group(1)}{m.group(2)}"
    return fallback


def _nearest_slot(day_slots: list, hour: int) -> dict | None:
    if not day_slots:
        return None
    return min(day_slots, key=lambda s: abs(int(s.get("hour", 0)) - hour))


def _conditions_from_slot(slot: dict | None, hour: int) -> dict | None:
    if not slot:
        return None
    cond = {"hour": int(slot.get("hour", hour)), "source": "windguru"}
    for key in ("wspd_kt", "wave_m", "wave_per_s", "dir_deg", "wave_dir_deg"):
        if key in slot and slot[key] is not None:
            try:
                cond[key] = float(slot[key])
            except (TypeError, ValueError):
                pass
    if len(cond) <= 2:
        return None
    return cond


def compress_thumb(src: Path, dest: Path, max_kb: int = 110) -> int:
    """Compress frame to JPEG ~80–120KB. Returns bytes written."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    for q in (5, 6, 7, 8, 10, 12):
        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(src),
            "-vf", "scale='min(960,iw)':-2",
            "-q:v", str(q),
            str(dest),
        ]
        try:
            subprocess.check_call(cmd)
        except Exception:
            break
        size = dest.stat().st_size if dest.exists() else 0
        if size and size <= max_kb * 1024:
            return size
    try:
        from PIL import Image
        im = Image.open(src).convert("RGB")
        w, h = im.size
        if w > 960:
            im = im.resize((960, int(h * 960 / w)), Image.Resampling.LANCZOS)
        for quality in (72, 65, 58, 50, 42):
            im.save(dest, "JPEG", quality=quality, optimize=True)
            size = dest.stat().st_size
            if size <= max_kb * 1024:
                return size
        return dest.stat().st_size
    except Exception as e:
        print("thumb fail", src, e)
        return 0


def compress_clip(src: Path, dest: Path, max_sec: float = 12.0) -> int:
    """Encode short muted H.264 web clip (~640w). Returns bytes written or 0."""
    if not src.exists():
        return 0
    dest.parent.mkdir(parents=True, exist_ok=True)
    import subprocess
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(src),
        "-t", str(max_sec),
        "-vf", "scale=640:-2",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "28",
        "-an", "-movflags", "+faststart",
        str(dest),
    ]
    try:
        subprocess.check_call(cmd)
        return dest.stat().st_size if dest.exists() else 0
    except Exception as e:
        print("clip fail", src, e)
        if dest.exists():
            dest.unlink(missing_ok=True)
        return 0


def _load_manifest(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _discover_runs(day_dir: Path) -> list[tuple[str, Path, dict]]:
    """Return list of (hhmm, run_dir, manifest) for a date folder.

    Timed runs: subdirs matching ^\\d{4}$ with at least one slug notes.json.
    Legacy: day root itself when it has slug notes.json (hhmm derived later).
    """
    runs: list[tuple[str, Path, dict]] = []
    # Timed HHMM runs first
    for child in sorted(day_dir.iterdir()):
        if not child.is_dir() or not HHMM_RE.match(child.name):
            continue
        if any((child / slug / "notes.json").exists() for slug in SLUG_TO_SPOT):
            man = _load_manifest(child / "manifest.json")
            runs.append((child.name, child, man))
    # Legacy day-root spots
    if any((day_dir / slug / "notes.json").exists() for slug in SLUG_TO_SPOT):
        man = _load_manifest(day_dir / "manifest.json")
        # placeholder hhmm; per-entry override from captured_at
        runs.append(("", day_dir, man))
    return runs


def _day_slots_for(
    spots_fc: dict,
    spot_name: str,
    date_s: str,
    run_dir: Path,
    day_dir: Path,
) -> list:
    day_slots = ((spots_fc.get(spot_name) or {}).get("days") or {}).get(date_s) or []
    for fc_path in (run_dir / "forecast.json", day_dir / "forecast.json"):
        if not fc_path.exists():
            continue
        try:
            af = json.loads(fc_path.read_text(encoding="utf-8"))
            alt = ((af.get("spots") or {}).get(spot_name) or {}).get("days") or {}
            if alt.get(date_s):
                return alt[date_s]
        except Exception:
            pass
    return day_slots


def build(forecast_path: Path | None = None) -> dict:
    forecast_path = forecast_path or FORECAST_SLOTS
    forecast = {}
    if forecast_path.exists():
        forecast = json.loads(forecast_path.read_text(encoding="utf-8"))
    spots_fc = (forecast.get("spots") or {})

    entries: list[dict] = []
    # Track latest thumb source per (date, slug) for flat live-card path
    latest_thumb: dict[tuple[str, str], tuple[str, Path]] = {}

    for day_dir in sorted(ARCHIVE_ROOT.iterdir()):
        if not day_dir.is_dir() or not DATE_RE.match(day_dir.name):
            continue
        date_s = day_dir.name
        for run_hhmm, run_dir, manifest in _discover_runs(day_dir):
            drive = manifest.get("drive") or {}
            date_folder_url = drive.get("viewUrl") or (
                DRIVE_FOLDER_TMPL.format(fid=drive["date_folder_id"])
                if drive.get("date_folder_id")
                else "https://drive.google.com/drive/folders/1Xdha_fYDEydI3tneJFZTQEXfLkjKxstW"
            )
            spot_folders = drive.get("spot_folders") or {}

            for slug, spot_name in SLUG_TO_SPOT.items():
                notes_path = run_dir / slug / "notes.json"
                frame_path = run_dir / slug / "frame.jpg"
                if not notes_path.exists() or not frame_path.exists():
                    continue
                notes = json.loads(notes_path.read_text(encoding="utf-8"))
                # Directory slug is canonical (ignore typos in notes.json)

                captured_at = notes.get("captured_at") or manifest.get("created_at")
                hour = _parse_captured_hour(captured_at)
                if hour is None:
                    hour = 11

                hhmm = run_hhmm or _hhmm_from_captured(captured_at, "0000")
                # Prefer manifest hhmm when present on timed runs
                if manifest.get("hhmm") and HHMM_RE.match(str(manifest["hhmm"])):
                    if run_hhmm:  # only for timed dirs
                        hhmm = str(manifest["hhmm"])

                day_slots = _day_slots_for(spots_fc, spot_name, date_s, run_dir, day_dir)
                slot = _nearest_slot(day_slots, hour)
                if slot is None and day_slots:
                    slot = _nearest_slot(day_slots, 11)
                conditions = _conditions_from_slot(slot, hour)

                # Unique timed thumb path
                thumb_rel = f"archive/{date_s}/{hhmm}/{slug}.jpg"
                thumb_dest = REPO_ARCHIVE / date_s / hhmm / f"{slug}.jpg"
                size = compress_thumb(frame_path, thumb_dest)
                print(f"thumb {thumb_rel} {size} bytes")

                clip_src = run_dir / slug / "clip.mp4"
                clip_rel = f"archive/{date_s}/{hhmm}/{slug}.mp4"
                clip_dest = REPO_ARCHIVE / date_s / hhmm / f"{slug}.mp4"
                clip_size = compress_clip(clip_src, clip_dest) if clip_src.exists() else 0
                if clip_size:
                    print(f"clip {clip_rel} {clip_size} bytes")

                spot_fid = spot_folders.get(slug)
                drive_url = (
                    DRIVE_FOLDER_TMPL.format(fid=spot_fid) if spot_fid else date_folder_url
                )

                entry = {
                    "date": date_s,
                    "slug": slug,
                    "spot": notes.get("spot") or spot_name,
                    "captured_at": captured_at,
                    "wave_notes_zh": notes.get("wave_notes_zh") or "",
                    "live_ok": bool(notes.get("live_ok", True)),
                    "thumb": thumb_rel,
                    
                }
                if clip_size:
                    entry["clip"] = clip_rel
                if conditions:
                    entry["conditions"] = conditions
                entries.append(entry)

                # Track latest for flat live-card copy
                key = (date_s, slug)
                prev = latest_thumb.get(key)
                if prev is None or (captured_at or "") > prev[0]:
                    latest_thumb[key] = (captured_at or "", thumb_dest)

    # Copy latest per slug to archive/{date}/{slug}.jpg (live cards convenience)
    for (date_s, slug), (_cap, src_thumb) in sorted(latest_thumb.items()):
        if not src_thumb.exists():
            continue
        flat = REPO_ARCHIVE / date_s / f"{slug}.jpg"
        flat.parent.mkdir(parents=True, exist_ok=True)
        flat.write_bytes(src_thumb.read_bytes())
        # Mirror beside archive day root for convenience
        day_flat = ARCHIVE_ROOT / date_s / f"{slug}.jpg"
        day_flat.write_bytes(src_thumb.read_bytes())
        print(f"latest flat archive/{date_s}/{slug}.jpg")

    # Stable order: date, hhmm (from thumb path), slug order
    slug_order = {s: i for i, s in enumerate(SLUG_TO_SPOT)}
    entries.sort(
        key=lambda e: (
            e.get("date") or "",
            e.get("captured_at") or "",
            slug_order.get(e.get("slug"), 99),
        )
    )

    payload = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "archive_spots": list(SLUG_TO_SPOT.keys()),
        "spot_map": SLUG_TO_SPOT,
        "entries": entries,
        "note_zh": "歷史樣本尚少，僅供參考" if len({e["date"] for e in entries}) <= 1 else "",
    }
    INDEX_OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    REPO_ARCHIVE.mkdir(parents=True, exist_ok=True)
    REPO_INDEX.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {INDEX_OUT} entries={len(entries)}")
    print(f"wrote {REPO_INDEX}")
    return payload


if __name__ == "__main__":
    build()
