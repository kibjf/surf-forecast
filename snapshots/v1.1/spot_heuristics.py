#!/usr/bin/env python3
"""Local surf-experience heuristics for surf-mode scoring.

Loads ``data/spot-heuristics.json`` (repo root or relative to this file).
Adjustments are intentionally smaller than the wave×10 / period×1.2 base so
they can swing close calls without dominating swell quality.

Spots with no JSON entry return a zero delta (scoring unchanged).
Wind-sport scoring should not call this module.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

TZ = timezone(timedelta(hours=8))

# Keep |delta| below ~0.8 m of wave height so swell remains primary.
MAX_ABS_DELTA = 8.0

CALM_KT = 2.5
SENSITIVE_KT = 4.5  # 翡翠灣: extra drag above ~4–5 kt
LITTLE_OR_NONE_PER_KT = 1.2
LITTLE_OR_NONE_CAP = 6.0
CALM_PREFER_PER_KT = 0.35
CALM_PREFER_CAP = 2.0
SENSITIVE_PER_KT = 1.4
SENSITIVE_CAP = 6.0
ALLOW_SOME_CREDIT_PER_KT = 0.25
ALLOW_SOME_CAP = 2.0
OFFSHORE_BONUS = 2.0
OFFSHORE_WIND_CREDIT_PER_KT = 0.25
OFFSHORE_WIND_CREDIT_CAP = 2.0
BAD_DIR_PENALTY = 3.0
WAVE_MIN_BONUS = 2.5
TIDE_WINDOW_BONUS = 2.5

# Compass sectors (degrees). N is wrap-around; end is exclusive so N ∩ NE = ∅.
DIR_SECTORS: dict[str, tuple[float, float]] = {
    "N": (337.5, 22.5),
    "北": (337.5, 22.5),
    "NE": (22.5, 67.5),
    "東北": (22.5, 67.5),
    "E": (67.5, 112.5),
    "東": (67.5, 112.5),
    "SE": (112.5, 157.5),
    "東南": (112.5, 157.5),
    "S": (157.5, 202.5),
    "南": (157.5, 202.5),
    "SW": (202.5, 247.5),
    "西南": (202.5, 247.5),
    "W": (247.5, 292.5),
    "西": (247.5, 292.5),
    "NW": (292.5, 337.5),
    "西北": (292.5, 337.5),
}

# Task: 中角 W/SW ≈ 225–292° (SW through W, before WNW).
W_SW_RANGE = (225.0, 292.0)

# Chinese / English labels from Windguru compass + JSON aliases.
_ZH_N = {"北", "北北西", "N", "NNW"}
_ZH_NE = {"東北", "東北東", "北北東", "NE", "ENE", "NNE"}
_ZH_E = {"東", "東北東", "東南東", "E", "ENE", "ESE"}
_ZH_W = {"西", "西南西", "西北西", "W", "WSW", "WNW"}
_ZH_SW = {"西南", "西南西", "南南西", "SW", "WSW", "SSW"}

_LABEL_ZH_GROUPS = {
    "N": _ZH_N,
    "北": _ZH_N,
    "NE": _ZH_NE,
    "東北": _ZH_NE,
    "E": _ZH_E,
    "東": _ZH_E,
    "W": _ZH_W,
    "西": _ZH_W,
    "SW": _ZH_SW,
    "西南": _ZH_SW,
}

_LOW_TYPES = {"乾潮", "低潮", "low", "low_tide"}
_HIGH_TYPES = {"滿潮", "高潮", "high", "high_tide"}

_CACHE: dict[str, Any] | None = None
_CACHE_PATH: Path | None = None


def resolve_heuristics_path(explicit: str | Path | None = None) -> Path:
    """Resolve spot-heuristics.json relative to repo root, this file, or cwd."""
    if explicit:
        return Path(explicit)
    here = Path(__file__).resolve().parent
    candidates = [
        here / "data" / "spot-heuristics.json",
        here.parent / "data" / "spot-heuristics.json",
        here.parent.parent / "data" / "spot-heuristics.json",  # snapshots/v1.1 → repo
        Path.cwd() / "data" / "spot-heuristics.json",
    ]
    for cand in candidates:
        if cand.is_file():
            return cand
    return here.parent.parent / "data" / "spot-heuristics.json"


def load_spot_heuristics(
    path: str | Path | None = None, *, reload: bool = False
) -> dict[str, Any]:
    """Load heuristics JSON. Empty ``spots`` on missing/invalid file (fail open)."""
    global _CACHE, _CACHE_PATH
    resolved = resolve_heuristics_path(path)
    if not reload and _CACHE is not None and _CACHE_PATH == resolved:
        return _CACHE
    try:
        data = json.loads(resolved.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("spots"), list):
            raise ValueError("heuristics JSON must have a spots list")
        _CACHE = data
        _CACHE_PATH = resolved
        return data
    except Exception as exc:
        print(f"spot_heuristics: failed to load {resolved}: {exc}")
        empty: dict[str, Any] = {"version": 1, "spots": []}
        _CACHE = empty
        _CACHE_PATH = resolved
        return empty


def _norm(name: str) -> str:
    return str(name).strip().lower()


def find_spot(spot_key: str | None, data: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Match SPOTS[].key / short / JSON names / id."""
    if not spot_key:
        return None
    data = data if data is not None else load_spot_heuristics()
    want = _norm(spot_key)
    if not want:
        return None
    for spot in data.get("spots") or []:
        aliases = [spot.get("id"), *(spot.get("names") or [])]
        if want in {_norm(a) for a in aliases if a}:
            return spot
    return None


def slot_local_dt(day: str | None, hour, tz=TZ) -> datetime | None:
    """Local datetime for a forecast slot (date + hour)."""
    if not day or hour is None:
        return None
    try:
        return datetime.strptime(f"{day} {int(hour):02d}", "%Y-%m-%d %H").replace(tzinfo=tz)
    except (TypeError, ValueError):
        return None


def tide_events_for_spot_day(
    tides: dict[str, Any] | None,
    spot_key: str | None,
    day: str | None,
    *,
    include_adjacent: bool = True,
) -> list[dict[str, Any]]:
    """Flatten 乾潮/滿潮 extrema for a spot, optionally ±1 calendar day."""
    if not tides or not spot_key or not day:
        return []
    rec = tides.get(spot_key) or {}
    days_map = rec.get("days") or {}
    keys = [day]
    if include_adjacent:
        try:
            d0 = datetime.strptime(day, "%Y-%m-%d")
            keys = [(d0 + timedelta(days=i)).strftime("%Y-%m-%d") for i in (-1, 0, 1)]
        except ValueError:
            keys = [day]
    out: list[dict[str, Any]] = []
    for d in keys:
        for ev in days_map.get(d) or []:
            item = dict(ev)
            item.setdefault("date", d)
            out.append(item)
    return out


def _deg_in_range(deg: float, start: float, end: float, *, end_exclusive: bool = False) -> bool:
    deg = deg % 360.0
    start = start % 360.0
    end = end % 360.0
    if start == end:
        return True
    if start < end:
        return start <= deg < end if end_exclusive else start <= deg <= end
    if end_exclusive:
        return deg >= start or deg < end
    return deg >= start or deg <= end


def _combined_w_sw(labels: Iterable[str]) -> bool:
    labs = {str(x).strip() for x in labels}
    return bool(labs & {"W", "西"}) and bool(labs & {"SW", "西南"})


def _dir_matches(
    labels: Iterable[str] | None,
    *,
    wind_dir_deg: float | None,
    wind_dir_zh: str | None,
) -> bool:
    labs = [str(x).strip() for x in (labels or []) if str(x).strip()]
    if not labs:
        return False
    if wind_dir_deg is not None:
        if _combined_w_sw(labs):
            return _deg_in_range(float(wind_dir_deg), W_SW_RANGE[0], W_SW_RANGE[1])
        for lab in labs:
            sector = DIR_SECTORS.get(lab)
            if not sector:
                continue
            start, end = sector
            # N is exclusive at 22.5° so NE/E offshore does not collide.
            exclusive = lab in ("N", "北")
            if _deg_in_range(float(wind_dir_deg), start, end, end_exclusive=exclusive):
                return True
        return False
    zh = (wind_dir_zh or "").replace("偏", "").strip()
    if not zh:
        return False
    for lab in labs:
        group = _LABEL_ZH_GROUPS.get(lab)
        if group and zh in group:
            return True
        if zh == lab:
            return True
    return False


def _parse_tide_dt(ev: dict[str, Any], fallback_day: str | None) -> datetime | None:
    raw = ev.get("datetime") or ev.get("DateTime")
    if raw:
        try:
            text = str(raw).replace("Z", "+00:00")
            dt = datetime.fromisoformat(text)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=TZ)
            return dt
        except ValueError:
            pass
    day = ev.get("date") or fallback_day
    time_s = ev.get("time") or ""
    if not day or not time_s:
        return None
    try:
        hh, mm, *_ = str(time_s).split(":")
        return datetime.strptime(f"{day} {int(hh):02d}:{int(mm):02d}", "%Y-%m-%d %H:%M").replace(
            tzinfo=TZ
        )
    except (TypeError, ValueError):
        return None


def _in_tide_window(
    slot_dt: datetime | None,
    events: Iterable[dict[str, Any]] | None,
    types: set[str],
    hours_before: float,
    hours_after: float,
) -> bool:
    if slot_dt is None or not events:
        return False
    fallback_day = slot_dt.strftime("%Y-%m-%d")
    for ev in events:
        et = str(ev.get("type") or ev.get("Tide") or "").strip()
        if et not in types:
            continue
        tdt = _parse_tide_dt(ev, fallback_day)
        if tdt is None:
            continue
        hours = (slot_dt - tdt).total_seconds() / 3600.0
        if -float(hours_before) <= hours <= float(hours_after):
            return True
    return False


def _offshore_reason(dirs: Iterable[str] | None) -> str:
    labs = {str(x).strip() for x in (dirs or [])}
    if labs & {"W", "SW", "西", "西南"}:
        return "西／西南偏 offshore"
    if labs & {"NE", "E", "東北", "東"}:
        return "東北／東偏 offshore"
    return "偏 offshore"


def _cap_delta(delta: float) -> float:
    if delta > MAX_ABS_DELTA:
        return MAX_ABS_DELTA
    if delta < -MAX_ABS_DELTA:
        return -MAX_ABS_DELTA
    return delta


def apply_spot_heuristics(
    spot_key: str | None,
    *,
    wind_kt: float | None = None,
    wind_dir_deg: float | None = None,
    wind_dir_zh: str | None = None,
    wave_height_m: float | None = None,
    slot_dt: datetime | None = None,
    tide_events: list[dict[str, Any]] | None = None,
) -> tuple[float, list[str]]:
    """Return (score_delta, short Chinese reasons) for surf-mode only.

    Reasons are already ranked (largest |component| first), at most two items,
    and omitted for tiny tweaks so callers can append one clause without spam.
    """
    spot = find_spot(spot_key)
    if not spot:
        return 0.0, []

    rules = spot.get("rules") or {}
    wind_rules = rules.get("wind") or {}
    tide_rules = rules.get("tide") or {}
    wave_rules = rules.get("wave_height_m") or {}

    parts: list[tuple[str, float, str]] = []  # id, delta, reason
    wind = float(wind_kt) if wind_kt is not None else None

    prefer = wind_rules.get("prefer")
    sensitive = bool(wind_rules.get("sensitive"))
    allow_some = bool(wind_rules.get("allow_some"))

    if wind is not None and allow_some:
        credit = min(max(wind, 0.0) * ALLOW_SOME_CREDIT_PER_KT, ALLOW_SOME_CAP)
        if credit:
            parts.append(("allow_wind", credit, "可有風"))

    if wind is not None and sensitive:
        # Extra drag starts ~4–5 kt; do not also apply the “must be calm” rule.
        if wind > SENSITIVE_KT:
            extra = min((wind - SENSITIVE_KT) * SENSITIVE_PER_KT, SENSITIVE_CAP)
            if extra:
                parts.append(("sensitive", -extra, "風敏感"))
    elif wind is not None and prefer == "little_or_none" and not allow_some and wind > CALM_KT:
        extra = min((wind - CALM_KT) * LITTLE_OR_NONE_PER_KT, LITTLE_OR_NONE_CAP)
        if extra:
            parts.append(("need_calm", -extra, "要沒風"))
    elif wind is not None and prefer == "calm" and not allow_some and wind > CALM_KT:
        extra = min((wind - CALM_KT) * CALM_PREFER_PER_KT, CALM_PREFER_CAP)
        if extra >= 1.0:
            parts.append(("prefer_calm", -extra, "沒風較佳"))

    offshore_dirs = wind_rules.get("offshore_dirs") or []
    if _dir_matches(offshore_dirs, wind_dir_deg=wind_dir_deg, wind_dir_zh=wind_dir_zh):
        parts.append(("offshore", OFFSHORE_BONUS, _offshore_reason(offshore_dirs)))
        if wind is not None and wind > 0:
            credit = min(wind * OFFSHORE_WIND_CREDIT_PER_KT, OFFSHORE_WIND_CREDIT_CAP)
            if credit:
                parts.append(("offshore_wind", credit, _offshore_reason(offshore_dirs)))

    bad_dirs = wind_rules.get("bad_dirs") or []
    if _dir_matches(bad_dirs, wind_dir_deg=wind_dir_deg, wind_dir_zh=wind_dir_zh):
        parts.append(("bad_dir", -BAD_DIR_PENALTY, "北風不宜"))

    min_ideal = wave_rules.get("min_ideal")
    if min_ideal is not None and wave_height_m is not None and wave_height_m >= float(min_ideal):
        parts.append(("wave_min", WAVE_MIN_BONUS, "浪高夠"))

    prefer_tide = tide_rules.get("prefer")
    if prefer_tide == "around_low":
        before = float(tide_rules.get("window_hours_before_low") or 2)
        after = float(tide_rules.get("window_hours_after_low") or 2)
        if _in_tide_window(slot_dt, tide_events, _LOW_TYPES, before, after):
            parts.append(("tide_low", TIDE_WINDOW_BONUS, "近乾潮"))
    elif prefer_tide == "around_high":
        before = float(tide_rules.get("window_hours_before_high") or 3)
        after = float(tide_rules.get("window_hours_after_high") or 2)
        if _in_tide_window(slot_dt, tide_events, _HIGH_TYPES, before, after):
            parts.append(("tide_high", TIDE_WINDOW_BONUS, "近滿潮"))

    raw = sum(d for _, d, _ in parts)
    delta = _cap_delta(raw)
    # Collapse duplicate reasons; drop tiny / generic "可有風" unless it is the only signal.
    ranked = sorted(parts, key=lambda p: abs(p[1]), reverse=True)
    reasons: list[str] = []
    for _pid, mag, text in ranked:
        if abs(mag) < 1.2:
            continue
        if text == "可有風":
            continue
        if text not in reasons:
            reasons.append(text)
        if len(reasons) >= 2:
            break
    if abs(delta) < 0.75:
        reasons = []
    return delta, reasons
