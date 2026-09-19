#!/usr/bin/env python3
"""Refresh Taiwan surf forecast data + page. Real fetches only."""
from __future__ import annotations

import json
import math
import re
import sys
import ssl
import subprocess
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from surf_archive_ui import (
    ARCHIVE_CSS,
    ensure_similar_archive_assets,
    load_similar_index,
    render_live_archive_html,
    render_similar_panel_shell,
    similar_index_js_const,
    similar_match_js,
)

TZ = timezone(timedelta(hours=8))
TODAY = "2026-09-19"
DAYS = [
    (datetime.strptime(TODAY, "%Y-%m-%d") + timedelta(days=i)).strftime("%Y-%m-%d")
    for i in range(5)
]
# Windguru cadence: start 03h, every 2 hours (03,05,…,23). Snap to nearest available when missing.
HOURS = list(range(3, 24, 2))  # 3,5,7,9,11,13,15,17,19,21,23
UA = "Mozilla/5.0 (compatible; kibjf-surf-forecast/1.0)"

SPOTS = [
    {
        "key": "後龍",
        "short": "後龍",
        "wg_id": 453788,
        "wg_name": "苗栗 後龍 外埔漁港",
        "region": "苗栗西岸",
        "caveat": "海岸：面向西／西北海域。北北東風多為側岸～偏離岸（相對西向海岸）（簡要參考，勿過度解讀）。",
        "tip_west": True,
        "accent": "#38bdf8",
        "tide_loc_id": "10005060",
        "tide_code": "T000506 / 10005060",
        "tide_station": "中央氣象署 · 苗栗縣後龍",
        "tide_label": "苗栗縣後龍",
        "tide_src": "https://www.cwa.gov.tw/V8/C/M/Fishery/tide_30day_MOD/T000506.html",
        "tide_note": None,
        "range_default": "潮差：小",
    },
    {
        "key": "竹南假日之森",
        "short": "假日之森",
        "wg_id": 167590,
        "wg_name": "竹南 - 假日之森",
        "region": "苗栗西岸",
        "caveat": "海岸：面向西／西北海域。北北東風多為側岸～偏離岸（簡要參考，勿過度解讀）。",
        "tip_west": True,
        "accent": "#2dd4bf",
        "tide_loc_id": "10005040",
        "tide_code": "T000504 / 10005040",
        "tide_station": "中央氣象署 · 苗栗縣竹南",
        "tide_label": "苗栗縣竹南",
        "tide_src": "https://www.cwa.gov.tw/V8/C/M/Fishery/tide_30day_MOD/T000504.html",
        "tide_note": None,
        "range_default": "潮差：小",
    },
    {
        "key": "松柏港",
        "short": "松柏港",
        "wg_id": 138043,
        "wg_name": "松柏港",
        "region": "台中大甲／大安",
        "caveat": "海岸：面向西／西北海域（大安溪口北側）。北北東風偏側岸～離岸；風強時與後龍類似易亂浪面（簡要參考，勿過度解讀）。",
        "tip_west": True,
        "accent": "#fbbf24",
        "tide_loc_id": "66000110",
        "tide_code": "T600011 / 66000110",
        "tide_station": "中央氣象署 · 臺中市大甲",
        "tide_label": "臺中市大甲",
        "tide_src": "https://www.cwa.gov.tw/V8/C/M/Fishery/tide_30day_MOD/T600011.html",
        "tide_note": "松柏港位於台中大甲區；大甲為最近鄉鎮潮汐站（苑裡／通霄亦可參考）",
        "range_default": "潮差：小",
    },
    {
        "key": "中角",
        "short": "中角",
        "wg_id": 167612,
        "wg_name": "金山 - 中角",
        "region": "新北北海岸（金山）",
        "caveat": "海岸：面向東北海域（金山中角灣）。偏北／東北湧浪較直接；南～西南風較乾淨（簡要參考，勿過度解讀）。",
        "tip_west": False,
        "accent": "#4ade80",
        "tide_loc_id": "65000270",
        "tide_code": "T500027 / 65000270",
        "tide_station": "中央氣象署 · 新北市金山",
        "tide_label": "新北市金山",
        "tide_src": "https://www.cwa.gov.tw/V8/C/M/Fishery/tide_30day_MOD/T500027.html",
        "tide_note": "中角位於金山；潮汐用金山鄉鎮站",
        "range_default": "潮差：小",
    },
    {
        "key": "翡翠灣",
        "short": "翡翠灣",
        "wg_id": 182903,
        "wg_name": "萬里-翡翠灣",
        "region": "新北北海岸（萬里）",
        "caveat": "海岸：面向北／東北海域（萬里翡翠灣）。東北湧浪較直接；風向變化大時浪面易亂（簡要參考，勿過度解讀）。",
        "tip_west": False,
        "accent": "#22d3ee",
        "tide_loc_id": "65000280",
        "tide_code": "T500028 / 65000280",
        "tide_station": "中央氣象署 · 新北市萬里",
        "tide_label": "新北市萬里",
        "tide_src": "https://www.cwa.gov.tw/V8/C/M/Fishery/tide_30day_MOD/T500028.html",
        "tide_note": None,
        "range_default": "潮差：小",
    },
    {
        "key": "石門婚紗廣場",
        "short": "石門婚紗",
        "wg_id": 345987,
        "wg_name": "石門 - 婚紗廣場 - 劉家肉粽 - Greenball",
        "region": "新北北海岸（石門）",
        "caveat": "海岸：面向北／西北海域（石門婚紗廣場／富貴角一帶）。偏北湧浪較直接；側岸風時浪面易亂（簡要參考，勿過度解讀）。",
        "tip_west": False,
        "accent": "#fb923c",
        "tide_loc_id": "65000220",
        "tide_code": "T500022 / 65000220",
        "tide_station": "中央氣象署 · 新北市石門",
        "tide_label": "新北市石門",
        "tide_src": "https://www.cwa.gov.tw/V8/C/M/Fishery/tide_30day_MOD/T500022.html",
        "tide_note": None,
        "range_default": "潮差：小",
    },
    {
        "key": "無尾港",
        "short": "無尾港",
        "wg_id": 167601,
        "wg_name": "蘇澳 - 無尾港",
        "region": "宜蘭東岸",
        "caveat": "海岸：面向東／東南海域。偏東湧浪較直接；北北東風偏側岸（簡要參考，勿過度解讀）。",
        "tip_west": False,
        "accent": "#a78bfa",
        "tide_loc_id": "10002030",
        "tide_code": "T000203 / 10002030",
        "tide_station": "中央氣象署 · 宜蘭縣蘇澳",
        "tide_label": "宜蘭縣蘇澳",
        "tide_src": "https://www.cwa.gov.tw/V8/C/M/Fishery/tide_30day_MOD/T000203.html",
        "tide_note": None,
        "range_default": "潮差：小（東岸潮差原本較小）",
    },
    {
        "key": "烏石",
        "short": "烏石",
        "wg_id": 331495,
        "wg_name": "Yilan-烏石港",
        "region": "宜蘭東岸",
        "caveat": "海岸：面向東／東北海域（烏石港北側／外側）。偏東湧浪較直接；風向變化大時浪面易亂（簡要參考，勿過度解讀）。",
        "tip_west": False,
        "accent": "#f472b6",
        "tide_loc_id": "10002040",
        "tide_code": "T000204 / 10002040",
        "tide_station": "中央氣象署 · 宜蘭縣頭城（烏石港最近鄉鎮站）",
        "tide_label": "宜蘭縣頭城",
        "tide_src": "https://www.cwa.gov.tw/V8/C/M/Fishery/tide_30day_MOD/T000204.html",
        "tide_note": None,
        "range_default": "潮差：小（東岸潮差原本較小）",
    },
]

# North-coast Windguru spots share one CWA live marker (富貴角浮標 C6AH2) on scatter + live cards.
NORTH_COAST_SHARED_LIVE = ("中角", "翡翠灣", "石門婚紗廣場")
NORTH_COAST_LIVE_LABEL = "富貴角"
NORTH_COAST_LIVE_ACCENT = "#86efac"

# Scatter-plot abbreviations (short names beside points)
SCATTER_ABBR = {
    "後龍": "後龍",
    "竹南假日之森": "假森",
    "松柏港": "松柏",
    "中角": "中角",
    "翡翠灣": "翡灣",
    "石門婚紗廣場": "石門",
    "無尾港": "無尾",
    "烏石": "烏石",
    "富貴角": "富貴",  # live only (北海岸三點共用)
}

COMPASS = [
    (0, "N", "北"), (22.5, "NNE", "北北東"), (45, "NE", "東北"), (67.5, "ENE", "東北東"),
    (90, "E", "東"), (112.5, "ESE", "東南東"), (135, "SE", "東南"), (157.5, "SSE", "南南東"),
    (180, "S", "南"), (202.5, "SSW", "南南西"), (225, "SW", "西南"), (247.5, "WSW", "西南西"),
    (270, "W", "西"), (292.5, "WNW", "西北西"), (315, "NW", "西北"), (337.5, "NNW", "北北西"),
]

# SSL: some CWA endpoints fail verify on this box; Windguru OK. Use unverified only for CWA.
_ssl_unverified = ssl.create_default_context()
_ssl_unverified.check_hostname = False
_ssl_unverified.verify_mode = ssl.CERT_NONE


def now_taipei() -> datetime:
    return datetime.now(TZ)


def deg_to_compass(deg: float | None):
    if deg is None:
        return None, None
    deg = deg % 360
    best = min(COMPASS, key=lambda c: min(abs(deg - c[0]), 360 - abs(deg - c[0])))
    return best[1], best[2]


def http_json(url: str, timeout=60, insecure=False):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": "https://www.windguru.cz/"})
    ctx = _ssl_unverified if insecure else None
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return json.loads(r.read().decode("utf-8"))


def curl_json(url: str, timeout=90):
    """Prefer curl for CWA (handles their TLS quirks)."""
    cmd = [
        "curl", "-sS", "-A", UA, "--max-time", str(timeout),
        "-H", "Accept: application/json", url,
    ]
    out = subprocess.check_output(cmd)
    return json.loads(out.decode("utf-8"))


def fetch_wg(spot_id: int, model_id: int):
    url = (
        f"https://www.windguru.cz/int/iapi.php?q=forecast"
        f"&id_spot={spot_id}&id_model={model_id}&id_client=wgapp"
    )
    return http_json(url, timeout=45)



def pick_hours_for_day(widx, day, preferred=None, max_delta=2):
    """Pick preferred Windguru 2-hourly slots for a day, snapping to nearest available within max_delta."""
    preferred = list(preferred or HOURS)
    available = sorted({h for (d, h) in widx.keys() if d == day})
    if not available:
        return []
    picked = []
    used = set()
    for ph in preferred:
        if ph in available and ph not in used:
            picked.append(ph)
            used.add(ph)
            continue
        cands = [h for h in available if h not in used and abs(h - ph) <= max_delta]
        if not cands:
            continue
        h = min(cands, key=lambda x: (abs(x - ph), x))
        picked.append(h)
        used.add(h)
    return picked


def index_by_local(fcst: dict):
    """Map (date, hour_local) -> index using initstamp + hours."""
    init = datetime.fromtimestamp(fcst["initstamp"], tz=timezone.utc)
    out = {}
    for i, hr in enumerate(fcst["hours"]):
        t = (init + timedelta(hours=hr)).astimezone(TZ)
        out[(t.strftime("%Y-%m-%d"), t.hour)] = i
    return out, init.astimezone(TZ)


def round1(x):
    if x is None:
        return None
    return round(float(x), 1)


def kt_to_ms(kt):
    return round(float(kt) * 0.514444, 1)


def fetch_all_windguru():
    fetched_at = now_taipei().isoformat(timespec="microseconds")
    spots_out = {}
    raw_spots = []
    model_init = None
    for sp in SPOTS:
        sid = sp["wg_id"]
        print(f"Windguru fetch {sp['key']} {sid} ...")
        wind = fetch_wg(sid, 3)
        wave = fetch_wg(sid, 84)
        wfc, vfc = wind["fcst"], wave["fcst"]
        widx, _ = index_by_local(wfc)
        vidx, _ = index_by_local(vfc)
        model_init = wfc.get("initdate")
        # also save micro html for archive
        try:
            html = subprocess.check_output(
                ["curl", "-sS", "-A", UA, "--max-time", "20", f"https://micro.windguru.cz/{sid}"],
                text=True,
            )
            Path(f"/workspace/windguru-data/{sid}_gfs.html").write_text(html, encoding="utf-8")
        except Exception as e:
            print("  micro html skip", e)

        Path(f"/workspace/windguru-data/{sid}_gfs.json").write_text(
            json.dumps(wind, ensure_ascii=False), encoding="utf-8"
        )
        Path(f"/workspace/windguru-data/{sid}_wave.json").write_text(
            json.dumps(wave, ensure_ascii=False), encoding="utf-8"
        )

        days = {}
        for day in DAYS:
            slots = []
            for hour in pick_hours_for_day(widx, day, HOURS):
                wi = widx.get((day, hour))
                vi = vidx.get((day, hour))
                if wi is None:
                    continue
                wspd = round1(wfc["WINDSPD"][wi])
                gust = round1(wfc["GUST"][wi])
                wdir = float(wfc["WINDDIR"][wi])
                dlab, dzh = deg_to_compass(wdir)
                tmp = round1(wfc.get("TMP", wfc.get("TMPE", [None]* (wi+1)))[wi])
                wave_m = wave_per = wave_dir_deg = None
                wlab = wzh = None
                if vi is not None:
                    # Prefer primary swell / significant wave height
                    wave_m = round1(vfc.get("HTSGW", [None])[vi] if "HTSGW" in vfc else vfc.get("WVHGT", [None])[vi])
                    wave_per = round1(vfc.get("PERPW", [None])[vi] if "PERPW" in vfc else vfc.get("WVPER", [None])[vi])
                    wave_dir_deg = float(vfc.get("DIRPW", [None])[vi] if "DIRPW" in vfc else vfc.get("WVDIR", [None])[vi])
                    wlab, wzh = deg_to_compass(wave_dir_deg)
                slots.append({
                    "hour": hour,
                    "wspd_kt": wspd,
                    "wspd_ms": kt_to_ms(wspd),
                    "gust_kt": gust,
                    "gust_ms": kt_to_ms(gust),
                    "dir": dlab,
                    "dir_zh": dzh,
                    "dir_deg": round(wdir, 1),
                    "wave_m": wave_m,
                    "wave_per_s": wave_per,
                    "wave_dir": wlab,
                    "wave_dir_zh": wzh,
                    "wave_dir_deg": round(wave_dir_deg, 1) if wave_dir_deg is not None else None,
                    "tmp_c": tmp,
                })
            days[day] = slots

        # meta from spot endpoint
        try:
            meta = http_json(
                f"https://www.windguru.cz/int/iapi.php?q=spot&id_spot={sid}&id_client=wgapp",
                timeout=30,
            )
            Path(f"/workspace/windguru-data/{sid}_meta.json").write_text(
                json.dumps(meta, ensure_ascii=False), encoding="utf-8"
            )
            lat, lon = meta.get("lat"), meta.get("lon")
            sst = meta.get("sst")
            name_wg = meta.get("spotname") or sp["wg_name"]
        except Exception:
            lat = lon = sst = None
            name_wg = sp["wg_name"]

        spots_out[sp["key"]] = {
            "id": sid,
            "name_wg": name_wg,
            "url": f"https://www.windguru.cz/{sid}",
            "lat": lat,
            "lon": lon,
            "sst_c": f"{sst} C" if sst is not None else None,
            "model": "GFS 13 km",
            "model_init": f"{model_init} UTC" if model_init and "UTC" not in str(model_init) else model_init,
            "days": days,
        }
        raw_spots.append({
            "id": sid,
            "url": f"https://www.windguru.cz/{sid}",
            "name_zh": sp["key"],
            "name_wg": name_wg,
            "lat": lat,
            "lon": lon,
            "sst_c": sst,
            "model": "GFS 13 km",
            "model_init": model_init,
            "days": days,
        })
        print(f"  ok slots day0={len(days.get(TODAY, []))}")

    forecast = {
        "fetched_at": fetched_at,
        "model": "GFS 13 km",
        "spots": spots_out,
        "tides": {},  # filled later
    }
    raw = {
        "fetched_at": fetched_at,
        "timezone": "Asia/Taipei (UTC+8)",
        "model": "GFS 13 km",
        "spots": raw_spots,
    }
    return forecast, raw, fetched_at, model_init


def fetch_tides():
    fetched_at = now_taipei().isoformat(timespec="microseconds")
    tides = {}
    KEY = "rdec-key-123-45678-011121314"
    for sp in SPOTS:
        lid = sp["tide_loc_id"]
        url = (
            "https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-A0021-001"
            f"?Authorization={KEY}&format=JSON&LocationId={lid}"
        )
        print(f"CWA tide {sp['key']} {lid} ...")
        d = curl_json(url, timeout=60)
        tf = d.get("records", {}).get("TideForecasts") or []
        if not tf:
            raise RuntimeError(f"No tide data for {lid}: {d.get('records', {}).keys()}")
        loc = tf[0]["Location"]
        daily = loc["TimePeriods"]["Daily"]
        days = {}
        range_note = sp["range_default"]
        for day in DAYS:
            hits = [x for x in daily if x["Date"] == day]
            if not hits:
                days[day] = []
                continue
            entry = hits[0]
            if entry.get("TideRange"):
                tr = entry["TideRange"]
                if "東岸" in sp["range_default"]:
                    range_note = f"潮差：{tr}（東岸潮差原本較小）"
                else:
                    range_note = f"潮差：{tr}"
            events = []
            for t in entry.get("Time") or []:
                dt = t["DateTime"]  # 2026-09-18T09:19:00+08:00
                hhmm = dt[11:16]
                h = t["TideHeights"]["AboveLocalMSL"]
                events.append({
                    "type": t["Tide"],
                    "time": hhmm,
                    "height_cm": int(h) if h == int(h) else h,
                })
            days[day] = events
        rec = {
            "station": sp["tide_station"],
            "station_code": sp["tide_code"],
            "source": sp["tide_src"],
            "days": days,
            "range_note": range_note,
            "fetched_at": fetched_at,
            "api": "F-A0021-001",
            "location_id": lid,
            "location_name": loc.get("LocationName"),
        }
        if sp["tide_note"]:
            rec["note"] = sp["tide_note"]
        tides[sp["key"]] = rec
        print(f"  ok {loc.get('LocationName')} days={list(days)}")
    return tides, fetched_at


def wind_class(kt):
    if kt is None:
        return "mod", ""
    if kt < 8:
        return "light", "hl"
    if kt < 15:
        return "mod", "hl"
    return "strong", ""


def weekday_zh(date_str):
    names = ["週一", "週二", "週三", "週四", "週五", "週六", "週日"]
    d = datetime.strptime(date_str, "%Y-%m-%d")
    return names[d.weekday()]


def fmt_day_title(date_str):
    d = datetime.strptime(date_str, "%Y-%m-%d")
    return f"{weekday_zh(date_str)} {d.month}/{d.day}"


PERIOD_BUCKETS = {
    "早": (5, 6, 7, 8, 9),
    "中": (10, 11, 12, 13, 14, 15),
    "晚": (16, 17, 18, 19, 20, 21),
}


def default_period_for_now(now=None):
    """Pick 早/中/晚 from current Taipei hour; fallback 中."""
    h = (now or now_taipei()).hour
    for name, hours in PERIOD_BUCKETS.items():
        if h in hours:
            return name
    return "中"


def slots_in_period(slots, period):
    """Slots whose hour falls in the period bucket (real data only)."""
    hours = PERIOD_BUCKETS.get(period) or ()
    return [
        s
        for s in (slots or [])
        if s.get("hour") in hours
        and s.get("wave_m") is not None
        and s.get("wspd_kt") is not None
    ]


def score_surf_slot(s, tip_west=True):
    """玩浪：乾淨優先。浪大但風大不一定好；風 >6 kt 重罰。

    score ≈ wave*10 + period*1.2 − soft wind − steep excess over 6 kt
    (+ daytime / east swell dir).
    """
    wave = s.get("wave_m") or 0
    per = s.get("wave_per_s") or 0
    wind = s.get("wspd_kt") or 0
    score = wave * 10 + per * 1.2
    # Light drag below 6 kt; steep penalty once wind dirties the face
    if wind <= 6:
        score -= wind * 0.5
    else:
        score -= 6 * 0.5 + (wind - 6) * 3.0
    if 6 <= (s.get("hour") or 0) <= 18:
        score += 2
    if not tip_west and s.get("wave_dir_deg") is not None:
        wd = s["wave_dir_deg"]
        if 45 <= wd <= 135:
            score += 3
    return score


def score_wind_slot(s, tip_west=True):
    """玩風：偏好風速。score ≈ wind*1.5 + gust*0.3 + wave*2 (+west/strong)."""
    wind = s.get("wspd_kt") or 0
    gust = s.get("gust_kt")
    if gust is None:
        gust = 0
    wave = s.get("wave_m") or 0
    score = wind * 1.5 + gust * 0.3 + wave * 2
    if wind < 12:
        score -= (12 - wind) * 1.2  # soft: too light
    if wind > 30:
        score -= (wind - 30) * 1.5  # soft: dangerous
    if tip_west and wind >= 16:
        score += 2
    return score


def badge_for_mode(mode, wind, wave):
    """Return (badge_text, badge_class) for surf/wind modes."""
    wind = wind if wind is not None else 0
    wave = wave if wave is not None else 0
    if mode == "surf":
        # User: wind over ~6 kt usually ruins the face
        if wind < 6 and wave >= 0.5:
            return "佳", "good"
        if wind < 10:
            return "可", "ok"
        return "風強", "weak"
    # wind sports
    if 16 <= wind <= 28:
        return "佳", "good"
    if 12 <= wind < 16 or 28 < wind <= 32:
        return "可", "ok"
    if wind < 12:
        return "偏弱", "weak"
    return "偏強", "weak"


def tip_for_pick(mode, sp, s):
    wind = s.get("wspd_kt") or 0
    wave = s.get("wave_m") or 0
    if mode == "surf":
        if wind < 10 and wave >= 0.6:
            return "風偏弱、浪夠用，較適合衝浪"
        if wind >= 16:
            return "風偏強浪面易亂；可改清晨或東岸"
        if sp["tip_west"]:
            return "西岸風況；衝浪抓風較弱時段"
        return "東岸視浪向；偏東湧較直接"
    # wind
    if wind < 12:
        return "風偏弱，風箏／風浪板可能不夠力"
    if wind > 30:
        return "風很強，注意安全與裝備等級"
    if sp["tip_west"] and wind >= 16:
        return "西岸風場較強，適合玩風"
    return "風速可用；留意陣風與浪高"


def _slot_pick_payload(sp, day, s, mode, score):
    badge, bclass = badge_for_mode(mode, s.get("wspd_kt"), s.get("wave_m"))
    return {
        "key": sp["key"],
        "short": sp["short"],
        "accent": sp["accent"],
        "tip_west": sp["tip_west"],
        "day": day,
        "hour": s["hour"],
        "wave_m": s.get("wave_m"),
        "wave_per_s": s.get("wave_per_s"),
        "wave_dir_zh": s.get("wave_dir_zh") or "",
        "wspd_kt": s.get("wspd_kt"),
        "gust_kt": s.get("gust_kt"),
        "dir_zh": s.get("dir_zh") or "",
        "badge": badge,
        "badge_class": bclass,
        "tip": tip_for_pick(mode, sp, s),
        "score": round(score, 2),
    }


def best_in_period_for_spot(slots, tip_west, mode):
    """Best real slot in period for one spot; None if empty."""
    scorer = score_surf_slot if mode == "surf" else score_wind_slot
    best = None
    best_score = -1e9
    for s in slots:
        sc = scorer(s, tip_west)
        if sc > best_score:
            best_score = sc
            best = (s, sc)
    return best


def compute_daily_best(forecast, today=None):
    """Precompute top-2 spots per (date, period, mode) from real forecast slots."""
    today = today or TODAY
    dates = []
    for sp in SPOTS:
        for d in (forecast["spots"][sp["key"]].get("days") or {}):
            if d not in dates:
                dates.append(d)
    dates.sort()

    date_labels = {}
    for d in dates:
        if d == today:
            date_labels[d] = "今日"
        else:
            dd = datetime.strptime(d, "%Y-%m-%d")
            date_labels[d] = f"{weekday_zh(d)} {dd.month}/{dd.day}"

    by = {}
    for day in dates:
        by[day] = {}
        for period in ("早", "中", "晚"):
            by[day][period] = {}
            for mode in ("surf", "wind"):
                ranked = []
                for sp in SPOTS:
                    day_slots = (forecast["spots"][sp["key"]].get("days") or {}).get(day) or []
                    cand = slots_in_period(day_slots, period)
                    hit = best_in_period_for_spot(cand, sp["tip_west"], mode)
                    if not hit:
                        continue
                    s, sc = hit
                    ranked.append(_slot_pick_payload(sp, day, s, mode, sc))
                ranked.sort(key=lambda x: x["score"], reverse=True)
                best = ranked[0] if ranked else None
                second = ranked[1] if len(ranked) > 1 else None
                by[day][period][mode] = {"best": best, "second": second}

    return {
        "dates": dates,
        "date_labels": date_labels,
        "periods": ["早", "中", "晚"],
        "modes": ["surf", "wind"],
        "default_period": default_period_for_now(),
        "default_mode": "surf",
        "by": by,
        "scoring_tip": (
            "玩浪：浪高×10＋週期×1.2；風≤6 kt 輕扣、>6 kt 重罰（浪大風大不一定好；東岸浪向 45–135°＋3）。"
            "玩風：風速×1.5＋陣風×0.3＋浪高×2（過弱／過強扣分；西岸強風＋2）。"
            "僅用實際預報時次，無資料則略過。"
        ),
    }



def best_slot_for_spot(days_map, tip_west=True):
    """Pick a highlight window for overview cards from real data."""
    best = None
    best_score = -1e9
    for day, slots in days_map.items():
        for s in slots:
            if s.get("wave_m") is None or s.get("wspd_kt") is None:
                continue
            # Prefer lower wind + decent wave + longer period for surfing
            score = score_surf_slot(s, tip_west)
            # Prefer daytime
            if 6 <= s["hour"] <= 18:
                score += 2
            # East coast: prefer E-ish wave
            if not tip_west and s.get("wave_dir_deg") is not None:
                wd = s["wave_dir_deg"]
                if 45 <= wd <= 135:
                    score += 3
            if score > best_score:
                best_score = score
                best = (day, s)
    return best


def _nearest_hour_slot(slots, target_hour):
    """Pick slot whose hour is closest to target_hour; ties → earlier hour."""
    if not slots:
        return None
    return min(slots, key=lambda s: (abs(int(s["hour"]) - target_hour), int(s["hour"])))


def _surf_score_tuple(it):
    """Align with score_surf_slot wind rule (6 kt threshold)."""
    _, wind, wave, per, *_ = it
    wind = wind or 0
    score = (wave or 0) * 10 + (per or 0) * 1.2
    if wind <= 6:
        score -= wind * 0.5
    else:
        score -= 6 * 0.5 + (wind - 6) * 3.0
    return score


def pick_tomorrow_morning_recommendation(forecast, target_hour=6):
    """Best surf pick near tomorrow ~06:00 (nearest Windguru hour, usually 05 or 07)."""
    if len(DAYS) < 2:
        return None, "明日預報尚未載入。"
    tomorrow = DAYS[1]
    east, west = [], []
    used_hour = None
    for sp in SPOTS:
        slots = forecast["spots"][sp["key"]]["days"].get(tomorrow) or []
        s = _nearest_hour_slot(slots, target_hour)
        if not s:
            continue
        if abs(int(s["hour"]) - target_hour) > 2:
            continue
        used_hour = int(s["hour"]) if used_hour is None else used_hour
        item = (
            sp["short"],
            s["wspd_kt"],
            s["wave_m"],
            s.get("wave_per_s"),
            s.get("dir_zh"),
            s.get("wave_dir_zh"),
            int(s["hour"]),
        )
        if sp["tip_west"]:
            west.append(item)
        else:
            east.append(item)

    if not east and not west:
        return None, "明日清晨尚無可用預報時次。"

    def score(it):
        return _surf_score_tuple(it[:6])

    pool = east if east else west
    # Prefer east when its best surf score beats west (same idea as today tip)
    if east and west:
        if score(max(east, key=score)) >= score(max(west, key=score)) or (
            min(e[1] for e in east) < 12 and max(w[1] for w in west) >= 14
        ):
            pool = east
        else:
            pool = west
    top = max(pool, key=score)
    pick = top[0]
    hour = top[6]
    rec = (
        f"明日早上約 {hour:02d}:00 首選 {pick}：風約 {top[1]:.0f} kt、"
        f"浪 {top[2]:.1f} m／{(top[3] or 0):.0f}s（{top[5] or ''}）。"
    )
    return pick, rec


def pick_today_recommendation(forecast, tides):
    """Short Traditional Chinese tip based on real today 09/12/15 data."""
    lines = []
    east = []
    west = []
    for sp in SPOTS:
        slots = forecast["spots"][sp["key"]]["days"].get(TODAY) or []
        by_h = {s["hour"]: s for s in slots}
        s15 = by_h.get(15) or by_h.get(12) or (slots[-1] if slots else None)
        if not s15:
            continue
        item = (sp["short"], s15["wspd_kt"], s15["wave_m"], s15.get("wave_per_s"), s15.get("dir_zh"), s15.get("wave_dir_zh"))
        if sp["tip_west"]:
            west.append(item)
        else:
            east.append(item)

    # Surfing preference: lower wind, usable wave
    def surf_score(it):
        return _surf_score_tuple(it)

    east_sorted = sorted(east, key=surf_score, reverse=True)
    west_sorted = sorted(west, key=lambda it: it[1], reverse=True)

    if east_sorted and (not west_sorted or surf_score(east_sorted[0]) >= surf_score(min(west, key=lambda it: it[1] if west else east_sorted[0]))):
        top = east_sorted[0]
        # If west wind is high and east wind low -> east for surfing
        west_wind = max((w[1] for w in west), default=0)
        east_wind = min((e[1] for e in east), default=99)
        if east_wind < 6 and west_wind >= 12:
            names = "／".join(e[0] for e in east_sorted[:2])
            rec = (
                f"衝浪優先 → 宜蘭東岸（{names}）：午後風約 "
                f"{east[0][1]:.0f}–{max(e[1] for e in east):.0f} kt，"
                f"浪約 {min(e[2] for e in east):.1f}–{max(e[2] for e in east):.1f} m、"
                f"週期約 {min(e[3] or 0 for e in east):.0f}–{max(e[3] or 0 for e in east):.0f}s。"
                f"西岸風偏強（約 {west_wind:.0f} kt）較適合風箏／風浪板，衝浪抓清晨。"
            )
            pick = names.split("／")[0]
        else:
            pick = top[0]
            rec = (
                f"今日首選 {pick}：風約 {top[1]:.0f} kt、浪 {top[2]:.1f} m／"
                f"{(top[3] or 0):.0f}s（{top[5] or ''}）。"
            )
    else:
        top = west_sorted[0] if west_sorted else east_sorted[0]
        pick = top[0]
        rec = f"今日首選 {pick}：風約 {top[1]:.0f} kt、浪 {top[2]:.1f} m。"
    return pick, rec


def collect_scatter_slider_slots(forecast):
    """Hours for the time slider: ~5 days of Windguru 2-hourly slots (03/05/…/23)."""
    preferred = list(HOURS)
    by_day = {}
    for sp in SPOTS:
        for day, day_slots in (forecast["spots"][sp["key"]].get("days") or {}).items():
            by_day.setdefault(day, set())
            for s in day_slots:
                by_day[day].add(int(s["hour"]))
    slots = []
    for day in sorted(by_day.keys()):
        hours = by_day[day]
        # Prefer exact preferred hours; else snap within 2h (later GFS often 3h).
        used = set()
        for ph in preferred:
            if ph in hours and ph not in used:
                slots.append((day, ph))
                used.add(ph)
                continue
            cands = [h for h in hours if h not in used and abs(h - ph) <= 2]
            if not cands:
                continue
            h = min(cands, key=lambda x: (abs(x - ph), x))
            slots.append((day, h))
            used.add(h)
    return slots


def _slot_label(date_s: str, hour: int) -> str:
    d = datetime.strptime(date_s, "%Y-%m-%d")
    return f"{d.month}/{d.day} {hour:02d}:00"


def _slot_date_label(date_s: str) -> str:
    d = datetime.strptime(date_s, "%Y-%m-%d")
    return f"{d.month}/{d.day}"


def _slider_day_marks(slider_slots):
    """One date label per day (mid-slot) + vertical separators at day boundaries.

    Returns (sep_html, tick_html). Positions are % along the range track
    (index / max_index), matching the range thumb geometry.
    """
    n = len(slider_slots)
    if n == 0:
        return "", ""
    groups = []  # [date, start_idx, end_idx]
    for i, s in enumerate(slider_slots):
        d = s.get("date") or ""
        if not groups or groups[-1][0] != d:
            groups.append([d, i, i])
        else:
            groups[-1][2] = i

    def pct(idx_f: float) -> float:
        if n <= 1:
            return 50.0
        return 100.0 * float(idx_f) / float(n - 1)

    seps = []
    for gi in range(1, len(groups)):
        prev_end = groups[gi - 1][2]
        next_start = groups[gi][1]
        mid = (prev_end + next_start) / 2.0
        seps.append(
            f'<span class="scatter-time-day-sep" style="left:{pct(mid):.2f}%"></span>'
        )

    ticks = []
    for date_s, start, end in groups:
        mid = (start + end) / 2.0
        lab = _slot_date_label(date_s) if date_s else ""
        ticks.append(
            f'<span class="scatter-time-day-tick" style="left:{pct(mid):.2f}%">{lab}</span>'
        )
    return "".join(seps), "".join(ticks)


def _scatter_abbr_for(name: str, short_map: dict) -> str:
    return SCATTER_ABBR.get(name) or short_map.get(name) or name


def _build_live_pts(cwa, short_map, colors):
    live_pts = []
    spots_cwa = (cwa or {}).get("spots") or {}
    if not spots_cwa and (cwa or {}).get("by_spot"):
        spots_cwa = {
            k: {"buoy": v.get("buoy") or {}, "coastal": v.get("coastal") or {}, "note": v.get("mapping_note") or ""}
            for k, v in cwa["by_spot"].items()
        }
    jitter = {
        "後龍": (-0.45, 0.04),
        "竹南假日之森": (0.45, -0.04),
        "松柏港": (0.0, 0.0),
        "無尾港": (0.0, 0.0),
        "烏石": (0.0, 0.0),
    }

    def _append_live(name, short_label, color, info, jx=0.0, jy=0.0, shared_for=None):
        buoy = (info.get("buoy") or {}).get("latest") or {}
        coastal = (info.get("coastal") or {}).get("latest") or {}
        wind_ms = buoy.get("wind_speed_ms")
        wind_deg = buoy.get("wind_dir_deg")
        wind_dir = buoy.get("wind_dir")
        if wind_ms is None:
            wind_ms = coastal.get("wind_speed_ms")
            wind_deg = coastal.get("wind_dir_deg")
            wind_dir = coastal.get("wind_dir")
        wave_m = buoy.get("wave_height_m")
        period = buoy.get("wave_period_s")
        wave_deg = buoy.get("wave_dir_deg")
        wave_dir = buoy.get("wave_dir")
        if wind_ms is None and wave_m is None:
            return
        x_raw = float(wind_ms) * 1.94384 if wind_ms is not None else None
        y_raw = float(wave_m) if wave_m is not None else None
        if x_raw is None or y_raw is None:
            return
        pt = {
            "name": name,
            "short": short_label,
            "abbr": _scatter_abbr_for(name, short_map),
            "series": "即時",
            "x": x_raw + jx,
            "y": y_raw + jy,
            "x_raw": x_raw,
            "y_raw": y_raw,
            "wind_deg": float(wind_deg) if wind_deg is not None else None,
            "wave_deg": float(wave_deg) if wave_deg is not None else None,
            "wind_dir": wind_dir,
            "wave_dir": wave_dir,
            "color": color,
            "obs_time": buoy.get("time") or coastal.get("time"),
            "jittered": (jx, jy) != (0, 0),
            "period_s": float(period) if period is not None else None,
        }
        if shared_for:
            pt["shared_for"] = list(shared_for)
            pt["buoy_id"] = "C6AH2"
        live_pts.append(pt)

    north_shared_emitted = False
    for sp in SPOTS:
        if sp["key"] in NORTH_COAST_SHARED_LIVE:
            if north_shared_emitted:
                continue
            info = None
            for nk in NORTH_COAST_SHARED_LIVE:
                cand = spots_cwa.get(nk) or {}
                if (cand.get("buoy") or {}).get("latest"):
                    info = cand
                    break
            if info is None:
                info = spots_cwa.get(sp["key"]) or {}
            _append_live(
                NORTH_COAST_LIVE_LABEL,
                NORTH_COAST_LIVE_LABEL,
                NORTH_COAST_LIVE_ACCENT,
                info,
                shared_for=NORTH_COAST_SHARED_LIVE,
            )
            north_shared_emitted = True
            continue
        jx, jy = jitter.get(sp["key"], (0, 0))
        _append_live(sp["key"], short_map[sp["key"]], colors[sp["key"]], spots_cwa.get(sp["key"]) or {}, jx, jy)
    return live_pts


def _build_forecast_pts(forecast, date_s, hour, short_map, colors):
    forecast_pts = []
    for sp in SPOTS:
        slots = forecast["spots"][sp["key"]]["days"].get(date_s) or []
        by_h = {int(s["hour"]): s for s in slots}
        s = by_h.get(hour)
        if not s:
            continue
        forecast_pts.append({
            "name": sp["key"],
            "short": short_map[sp["key"]],
            "abbr": _scatter_abbr_for(sp["key"], short_map),
            "series": "預報",
            "x": float(s["wspd_kt"]),
            "y": float(s["wave_m"]),
            "x_raw": float(s["wspd_kt"]),
            "y_raw": float(s["wave_m"]),
            "wind_deg": float(s["dir_deg"]),
            "wave_deg": float(s["wave_dir_deg"]) if s.get("wave_dir_deg") is not None else None,
            "wind_dir": s.get("dir"),
            "wave_dir": s.get("wave_dir"),
            "hour": hour,
            "date": date_s,
            "color": colors[sp["key"]],
            "period_s": float(s["wave_per_s"]) if s.get("wave_per_s") is not None else None,
        })
    return forecast_pts


def _nudge_forecast_away_from_live(forecast_pts, live_pts):
    """Nudge forecast only so live diamonds can stay fixed across slider hours."""
    fc_by = {p["name"]: p for p in forecast_pts}
    for lp in live_pts:
        targets = []
        if lp.get("shared_for"):
            targets = [fc_by[n] for n in lp["shared_for"] if n in fc_by]
        elif lp["name"] in fc_by:
            targets = [fc_by[lp["name"]]]
        for fp in targets:
            if abs(fp["x"] - lp["x"]) < 1.2 and abs(fp["y"] - lp["y"]) < 0.15:
                fp["x"] = fp["x"] + 0.55
                fp["y"] = fp["y"] + 0.08
                fp["overlap_nudged"] = True
                break


LABEL_OFFSETS = {
    ("後龍", False): (12, -10),
    ("竹南假日之森", False): (12, 12),
    ("松柏港", False): (12, -10),
    ("中角", False): (12, -10),
    ("翡翠灣", False): (12, 12),
    ("石門婚紗廣場", False): (-12, -10),
    ("無尾港", False): (12, -10),
    ("烏石", False): (12, 12),
    ("後龍", True): (-12, 12),
    ("竹南假日之森", True): (12, 12),
    ("松柏港", True): (-12, -10),
    ("富貴角", True): (12, -10),
    ("無尾港", True): (12, 12),
    ("烏石", True): (-12, 12),
}


def render_scatter_svg(forecast, cwa, target_hour=15, target_date=None):
    """Handcrafted SVG + multi-hour JSON for client-side time scrubbing.

    Live diamonds stay fixed; forecast circles/arrows/abbr update with the slider.
    Axis limits are fixed across all slider hours for smooth scrubbing.
    """
    colors = {sp["key"]: sp["accent"] for sp in SPOTS}
    short_map = {sp["key"]: sp["short"] for sp in SPOTS}
    target_date = target_date or TODAY

    live_base = _build_live_pts(cwa, short_map, colors)
    slider_keys = collect_scatter_slider_slots(forecast)
    if not slider_keys:
        slider_keys = [(TODAY, target_hour)]

    # Build per-slot forecast (nudge against a fresh live copy each time so live stays fixed in payload)
    slots_out = []
    all_xs, all_ys = [], []
    for date_s, hour in slider_keys:
        fc_n = _build_forecast_pts(forecast, date_s, hour, short_map, colors)
        _nudge_forecast_away_from_live(fc_n, live_base)
        slots_out.append({
            "date": date_s,
            "hour": hour,
            "label": _slot_label(date_s, hour),
            "forecast": fc_n,
        })
        for p in fc_n:
            all_xs.append(p["x"])
            all_ys.append(p["y"])
    for p in live_base:
        all_xs.append(p["x"])
        all_ys.append(p["y"])

    # Default index: prefer today 15:00, else nearest hour today, else first
    default_index = 0
    best = None
    for i, (date_s, hour) in enumerate(slider_keys):
        if date_s == target_date and hour == target_hour:
            default_index = i
            best = i
            break
        if date_s == target_date:
            dist = abs(hour - target_hour)
            if best is None or dist < abs(slider_keys[best][1] - target_hour) or (
                dist == abs(slider_keys[best][1] - target_hour) and hour < slider_keys[best][1]
            ):
                best = i
    if best is not None and not any(
        d == target_date and h == target_hour for d, h in slider_keys
    ):
        default_index = best

    default_slot = slots_out[default_index]
    forecast_pts = default_slot["forecast"]
    live_pts = live_base  # fixed across scrubbing

    xmin, xmax = max(0, min(all_xs) - 2), max(all_xs) + 3
    ymin, ymax = max(0.2, min(all_ys) - 0.35), max(all_ys) + 0.45

    W, H = 980, 600
    ox, oy, pw, ph = 58, 58, 880, 460
    MARKER_R = 8.0
    ARROW_LEN = 40.0

    def xmap(x):
        return ox + (x - xmin) / (xmax - xmin) * pw

    def ymap(y):
        return oy + ph - (y - ymin) / (ymax - ymin) * ph

    def arrow_line(x, y, deg_from, color, length=ARROW_LEN):
        if deg_from is None:
            return ""
        flow = (deg_from + 180) % 360
        rad = math.radians(flow)
        dx = math.sin(rad) * length
        dy = -math.cos(rad) * length
        gap = 0.22
        x0, y0 = x + dx * gap, y + dy * gap
        x1, y1 = x + dx, y + dy
        return (
            f'<line x1="{x0:.1f}" y1="{y0:.1f}" x2="{x1:.1f}" y2="{y1:.1f}" '
            f'stroke="{color}" stroke-width="2.4" marker-end="url(#arrow-{color.replace("#","")})" />'
        )

    marker_colors = {"38bdf8": "#38bdf8", "fbbf24": "#fbbf24"}
    markers = []
    for mid, col in marker_colors.items():
        markers.append(
            f'<marker id="arrow-{mid}" viewBox="0 0 10 10" refX="8" refY="5" '
            f'markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
            f'<path d="M0,0 L10,5 L0,10 z" fill="{col}"/></marker>'
        )

    def band(x0, x1, color):
        xa, xb = xmap(max(xmin, x0)), xmap(min(xmax, x1))
        if xb <= xa:
            return ""
        return f'<rect x="{xa:.1f}" y="{oy}" width="{xb-xa:.1f}" height="{ph}" fill="{color}" opacity="0.07"/>'

    def_hour = default_slot["hour"]
    def_date = default_slot["date"]
    title_prefix = "今日" if def_date == TODAY else _slot_label(def_date, def_hour).split()[0]
    title_text = (
        f'{title_prefix} {def_hour:02d}:00 風速 × 浪高　預報 vs 即時浮標'
        if def_date == TODAY
        else f'{default_slot["label"]} 風速 × 浪高　預報 vs 即時浮標'
    )

    parts = [
        f'<svg id="wws-svg" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" role="img" '
        f'aria-label="風速與浪高散佈圖，可拖曳時間軸切換預報時次" '
        f'style="width:100%;height:auto;display:block">',
        f'<rect width="{W}" height="{H}" fill="#0b1220" rx="16"/>',
        f'<rect x="{ox}" y="{oy}" width="{pw}" height="{ph}" fill="#111a2e" rx="8"/>',
        band(xmin, 8, "#34d399"),
        band(8, 15, "#fbbf24"),
        band(15, xmax + 1, "#fb7185"),
        '<defs>' + "".join(markers) + "</defs>",
        f'<text id="wws-title" x="{ox}" y="24" fill="#e2e8f0" font-size="16" font-weight="700" '
        f'font-family="Noto Sans TC,system-ui,sans-serif">{title_text}</text>',
        f'<text x="{ox}" y="44" fill="#8b9bb4" font-size="11" font-family="Noto Sans TC,system-ui,sans-serif">'
        f'圓點＝預報 · 菱形＝即時 · 縮寫標在點旁 · 箭頭為去向（北風→朝南；北=0°、東=90°）· 青＝風 · 金＝浪 · 拖曳下方時間軸切換預報時次</text>',
    ]

    for gx in range(int(math.ceil(xmin)), int(math.floor(xmax)) + 1, 2):
        xx = xmap(gx)
        parts.append(f'<line x1="{xx:.1f}" y1="{oy}" x2="{xx:.1f}" y2="{oy+ph}" stroke="#1e3a5f" stroke-dasharray="4 4" opacity="0.7"/>')
        parts.append(f'<text x="{xx:.1f}" y="{oy+ph+18}" text-anchor="middle" fill="#8b9bb4" font-size="11">{gx}</text>')
    for gy in [round(ymin + i * 0.2, 1) for i in range(0, 20)]:
        if gy < ymin or gy > ymax:
            continue
        yy = ymap(gy)
        parts.append(f'<line x1="{ox}" y1="{yy:.1f}" x2="{ox+pw}" y2="{yy:.1f}" stroke="#1e3a5f" stroke-dasharray="4 4" opacity="0.5"/>')
        parts.append(f'<text x="{ox-8}" y="{yy:.1f}" text-anchor="end" dominant-baseline="middle" fill="#8b9bb4" font-size="11">{gy:.1f}</text>')

    parts.append(f'<text x="{ox + pw/2:.0f}" y="{oy+ph+34}" text-anchor="middle" fill="#e2e8f0" font-size="12">風速（kt）</text>')
    parts.append(f'<text x="{ox-6}" y="{oy-4}" text-anchor="end" fill="#8b9bb4" font-size="11">浪高 m</text>')

    def point_markup(p, shape="circle"):
        chunks = []
        x, y = xmap(p["x"]), ymap(p["y"])
        r = MARKER_R
        if p.get("wind_deg") is not None:
            chunks.append(arrow_line(x, y, p["wind_deg"], "#38bdf8", ARROW_LEN))
        if p.get("wave_deg") is not None:
            chunks.append(arrow_line(x, y, p["wave_deg"], "#fbbf24", ARROW_LEN))
        if shape == "circle":
            chunks.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="{p["color"]}" '
                f'stroke="#fff" stroke-width="1.6" opacity="0.95"/>'
            )
        else:
            d = r * 1.15
            pts = f"{x:.1f},{y-d:.1f} {x+d:.1f},{y:.1f} {x:.1f},{y+d:.1f} {x-d:.1f},{y:.1f}"
            chunks.append(
                f'<polygon points="{pts}" fill="{p["color"]}" stroke="#fff" stroke-width="1.5" opacity="0.92"/>'
            )
        return "".join(chunks)

    def label_markup(p, live: bool):
        px, py = xmap(p["x"]), ymap(p["y"])
        dx, dy = LABEL_OFFSETS.get((p["name"], live), (12, -10))
        anchor = "start" if dx >= 0 else "end"
        lx = px + MARKER_R + 6 if dx >= 0 else px - MARKER_R - 6
        ly = py + dy
        abbr = p.get("abbr") or _scatter_abbr_for(p["name"], short_map)
        label = f"{abbr}·即" if live else abbr
        return (
            f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="{anchor}" '
            f'dominant-baseline="central" fill="{p["color"]}" font-size="11" font-weight="700" '
            f'font-family="Noto Sans TC,system-ui,sans-serif" stroke="#0b1220" stroke-width="3" '
            f'paint-order="stroke">{label}</text>'
        )

    # Forecast layer (JS replaces contents on scrub)
    parts.append('<g id="wws-forecast-layer">')
    for p in forecast_pts:
        parts.append(point_markup(p, "circle"))
    for p in forecast_pts:
        parts.append(label_markup(p, False))
    parts.append("</g>")

    # Live layer (fixed)
    parts.append('<g id="wws-live-layer">')
    for p in live_pts:
        parts.append(point_markup(p, "diamond"))
    for p in live_pts:
        parts.append(label_markup(p, True))
    parts.append("</g>")

    ly = oy + ph + 50
    parts.append(f'<circle cx="90" cy="{ly}" r="7" fill="#94a3b8" stroke="#fff"/>')
    parts.append(f'<text x="106" y="{ly+4}" fill="#e2e8f0" font-size="11" font-family="Noto Sans TC,system-ui,sans-serif">預報</text>')
    parts.append(f'<polygon points="160,{ly-7} 167,{ly} 160,{ly+7} 153,{ly}" fill="#94a3b8" stroke="#fff"/>')
    parts.append(f'<text x="176" y="{ly+4}" fill="#e2e8f0" font-size="11" font-family="Noto Sans TC,system-ui,sans-serif">即時</text>')
    parts.append(f'<line x1="230" y1="{ly}" x2="255" y2="{ly}" stroke="#38bdf8" stroke-width="2.2"/>')
    parts.append(f'<text x="262" y="{ly+4}" fill="#e2e8f0" font-size="11" font-family="Noto Sans TC,system-ui,sans-serif">風向去向</text>')
    parts.append(f'<line x1="340" y1="{ly}" x2="365" y2="{ly}" stroke="#fbbf24" stroke-width="2.2"/>')
    parts.append(f'<text x="372" y="{ly+4}" fill="#e2e8f0" font-size="11" font-family="Noto Sans TC,system-ui,sans-serif">浪向去向</text>')

    cwa_at = (cwa or {}).get("fetched_at", "")[:16].replace("T", " ")
    parts.append(
        f'<text id="wws-foot" x="{W/2:.0f}" y="{H - 18}" text-anchor="middle" fill="#64748b" font-size="10" '
        f'font-family="Noto Sans TC,system-ui,sans-serif">'
        f'預報 {default_slot["label"]} 台北｜即時約 {cwa_at}｜'
        f'北海岸三點即時共用富貴角（只顯示一點）｜後龍／假日之森共用新竹略偏移｜'
        f'綠&lt;8kt／黃8–14／紅≥15</text>'
    )
    parts.append("</svg>")

    label_offsets_json = {
        f"{name}|{'live' if live else 'fc'}": [dx, dy]
        for (name, live), (dx, dy) in LABEL_OFFSETS.items()
    }

    scatter_json = {
        "slots": slots_out,
        "live": live_base,  # fixed positions (pre-nudge); client keeps live layer static
        "default_index": default_index,
        "hour": def_hour,
        "date": def_date,
        "forecast": forecast_pts,
        "abbr": SCATTER_ABBR,
        "axis": {
            "xmin": xmin, "xmax": xmax, "ymin": ymin, "ymax": ymax,
            "W": W, "H": H, "ox": ox, "oy": oy, "pw": pw, "ph": ph,
            "marker_r": MARKER_R, "arrow_len": ARROW_LEN,
        },
        "label_offsets": label_offsets_json,
        "cwa_at": cwa_at,
        "today": TODAY,
        "slider_hours": [
            {"date": d, "hour": h, "label": _slot_label(d, h)} for d, h in slider_keys
        ],
    }
    return "\n".join(parts), scatter_json

def build_html(forecast, tides, cwa, svg, wg_fetched, cwa_fetched, pick, rec, pick_tm=None, rec_tm=None):
    rec_tm_html = rec_tm or ""
    if pick_tm and rec_tm:
        pick_tm_line = rec_tm
    elif rec_tm:
        pick_tm_line = rec_tm
    else:
        pick_tm_line = "明日清晨預報尚不足"

    # Reuse CSS from existing page
    old = Path("/workspace/surf-forecast.html").read_text(encoding="utf-8")
    m = re.search(r"<style>(.*?)</style>", old, re.S)
    style = m.group(1) if m else ""
    # Drop previous numbered-legend / side-layout CSS (option 3 uses on-SVG callouts)
    style = re.sub(r"\.scatter-layout[^{]*\{[^}]*\}", "", style)
    style = re.sub(r"\.scatter-key[^{]*\{[^}]*\}", "", style)
    style = re.sub(r"\.scatter-key\s+[^{\n]+\{[^}]*\}", "", style)
    # Remove @media block that only styles scatter-layout (best-effort)
    style = re.sub(
        r"@media\s*\(min-width:\s*900px\)\s*\{(?:[^{}]|\{[^{}]*\})*?\.scatter-layout(?:[^{}]|\{[^{}]*\})*?\}",
        "",
        style,
        flags=re.S,
    )
    # 8 spots: flexible overview / sea-card grids
    style = re.sub(
        r"\.overview\s*\{[^}]*grid-template-columns:\s*repeat\(5,\s*1fr\)[^}]*\}",
        ".overview {\n  display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; margin-bottom: 8px;\n}",
        style,
        count=1,
    )
    style = re.sub(
        r"\.sea-cards\s*\{[^}]*grid-template-columns:\s*repeat\(5,\s*1fr\)[^}]*\}",
        ".sea-cards {\n  display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px;\n}",
        style,
        count=1,
    )

    # Scatter table (mobile-friendly); callouts live on the SVG
    if ".scatter-table" not in style:
        style += """
.scatter-svg-wrap { width:100%; overflow-x:auto; -webkit-overflow-scrolling:touch; }
.scatter-table { margin-top:8px; }
.scatter-table summary { cursor:pointer; color:var(--muted); font-size:0.8rem; }
.scatter-table table { width:100%; border-collapse:collapse; font-size:0.8rem; margin-top:8px; }
.scatter-table th, .scatter-table td { padding:6px 8px; border-bottom:1px solid var(--line); text-align:left; }
.scatter-table .abbr { color:var(--muted); font-size:0.72rem; font-weight:600; }
.scatter-table .tag {
  display:inline-block; padding:1px 6px; border-radius:999px;
  font-size:0.68rem; font-weight:700; border:1px solid currentColor;
}
.scatter-table .tag-fc { color:#7dd3fc; }
.scatter-table .tag-live { color:#fbbf24; }
"""

    # Always refresh time-slider CSS (day labels + day-boundary separators)
    style = re.sub(
        r"/\* scatter-time-css \*/.*?/\* /scatter-time-css \*/",
        "",
        style,
        flags=re.S,
    )
    style = re.sub(r"\.scatter-time[^{]*\{[^}]*\}", "", style)
    style = re.sub(r"\.scatter-time\s+[^{\n]+\{[^}]*\}", "", style)
    style = re.sub(
        r"@media\s*\(max-width:\s*560px\)\s*\{\s*\.scatter-time[^}]*\}\s*\.scatter-time-now[^}]*\}\s*\}",
        "",
        style,
        flags=re.S,
    )
    style += """
/* scatter-time-css */
.scatter-time {
  margin: 12px 0 4px; padding: 12px 14px; border-radius: 12px;
  background: rgba(15, 23, 42, 0.65); border: 1px solid var(--line, #1e3a5f);
}
.scatter-time-row {
  display: flex; flex-wrap: wrap; align-items: baseline; gap: 10px 14px;
  margin-bottom: 6px;
}
.scatter-time-label {
  font-size: 0.85rem; font-weight: 700; color: var(--text, #e2e8f0);
  letter-spacing: 0.02em; white-space: nowrap;
}
.scatter-time-now {
  font-family: "JetBrains Mono", ui-monospace, monospace;
  font-size: 1.2rem; font-weight: 700; color: #7dd3fc;
  min-width: 7.5rem; letter-spacing: 0.01em;
}
.scatter-time-track-wrap {
  position: relative;
  width: 100%;
  padding: 4px 0;
}
.scatter-time-day-seps {
  position: absolute; left: 11px; right: 11px; top: 0; bottom: 0;
  pointer-events: none; z-index: 1;
}
.scatter-time-day-sep {
  position: absolute; top: 50%; left: 0;
  width: 2px; height: 18px; margin-top: -9px;
  background: rgba(148, 163, 184, 0.65);
  border-radius: 1px;
  transform: translateX(-50%);
  box-shadow: 0 0 0 1px rgba(15, 23, 42, 0.35);
}
.scatter-time input[type=range] {
  position: relative; z-index: 2;
  display: block; width: 100%; height: 28px; margin: 0;
  -webkit-appearance: none; appearance: none; background: transparent; cursor: pointer;
}
.scatter-time input[type=range]:focus { outline: none; }
.scatter-time input[type=range]::-webkit-slider-runnable-track {
  height: 6px; border-radius: 999px; background: linear-gradient(90deg,#1e3a5f,#334155);
}
.scatter-time input[type=range]::-webkit-slider-thumb {
  -webkit-appearance: none; appearance: none; width: 22px; height: 22px; margin-top: -8px;
  border-radius: 50%; background: #38bdf8; border: 2px solid #e2e8f0; box-shadow: 0 0 0 3px rgba(56,189,248,.25);
}
.scatter-time input[type=range]::-moz-range-track {
  height: 6px; border-radius: 999px; background: #1e3a5f; border: none;
}
.scatter-time input[type=range]::-moz-range-thumb {
  width: 22px; height: 22px; border-radius: 50%; background: #38bdf8;
  border: 2px solid #e2e8f0;
}
.scatter-time-ticks {
  position: relative;
  height: 1.15rem;
  margin: 2px 11px 0;
  font-size: 0.72rem; color: var(--muted, #8b9bb4);
}
.scatter-time-day-tick {
  position: absolute; top: 0;
  transform: translateX(-50%);
  white-space: nowrap; font-weight: 600; letter-spacing: 0.02em;
  pointer-events: none;
}
@media (max-width: 560px) {
  .scatter-time { padding: 10px 12px; }
  .scatter-time-now { font-size: 1.05rem; }
}
/* /scatter-time-css */
"""
    # Refresh archive/similar CSS
    style = re.sub(
        r"/\* archive-live-css \*/.*?/\* /archive-live-css \*/",
        "",
        style,
        flags=re.S,
    )
    style += ARCHIVE_CSS
    # daily-best controls / day cards
    style = re.sub(
        r"/\* daily-best-css \*/.*?/\* /daily-best-css \*/",
        "",
        style,
        flags=re.S,
    )
    style += """
/* daily-best-css */
.daily-best { margin-bottom: 8px; }
.daily-best-bar {
  display: flex; flex-wrap: wrap; gap: 10px 14px; align-items: center;
  margin: 4px 0 10px;
}
.seg {
  display: inline-flex; padding: 3px; gap: 2px;
  background: rgba(15, 23, 42, 0.75); border: 1px solid var(--line);
  border-radius: 999px;
}
.seg-btn {
  appearance: none; border: 0; cursor: pointer;
  background: transparent; color: var(--muted);
  font-family: inherit; font-size: 0.88rem; font-weight: 700;
  padding: 7px 14px; border-radius: 999px; letter-spacing: 0.02em;
  transition: background .15s, color .15s;
}
.seg-btn.is-on {
  background: linear-gradient(135deg, rgba(56,189,248,0.28), rgba(45,212,191,0.22));
  color: var(--text); box-shadow: 0 0 0 1px rgba(56,189,248,0.35);
}
.seg-btn:focus-visible { outline: 2px solid var(--cyan); outline-offset: 2px; }
.daily-best-tip {
  margin: 0 0 12px; font-size: 0.75rem; color: var(--muted); line-height: 1.45;
}
.daily-best-grid {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px;
}
.day-rec-card {
  background: linear-gradient(165deg, var(--card) 0%, var(--card2) 100%);
  border: 1px solid var(--line); border-top: 3px solid var(--accent, var(--cyan));
  border-radius: var(--radius); padding: 14px 14px 12px;
  box-shadow: 0 8px 28px rgba(0,0,0,0.25); min-height: 148px;
}
.day-rec-card .ov-name { font-size: 1.15rem; font-weight: 800; margin: 2px 0 4px; }
.day-rec-card .ov-slot {
  font-family: "JetBrains Mono", monospace; font-size: 0.82rem;
  color: var(--cyan); margin-bottom: 8px;
}
.day-rec-card .ov-second {
  margin-top: 8px; font-size: 0.75rem; color: var(--muted);
}
.pick-block-top { margin: 0 0 18px; }
.pick-tomorrow { margin: 8px 0 0; color: var(--muted, #8b9bb4); font-size: 0.92rem; }
.pick-block-top h2.section { margin-top: 8px; }
@media (max-width: 560px) {
  .seg-btn { padding: 6px 12px; font-size: 0.82rem; }
  .daily-best-tip { font-size: 0.7rem; }
}
/* /daily-best-css */
"""



    wg_t = wg_fetched[11:16] if len(wg_fetched) > 16 else wg_fetched
    cwa_t = cwa_fetched[11:16] if len(cwa_fetched) > 16 else cwa_fetched
    model_init = next(iter(forecast["spots"].values())).get("model_init", "")

    # Daily best recommendations (replaces per-spot overview grid)
    daily_best = compute_daily_best(forecast, TODAY)
    daily_best_js = json.dumps(daily_best, ensure_ascii=False)
    default_period = daily_best["default_period"]
    default_mode = daily_best["default_mode"]

    def _period_btn(label, cur):
        on = " is-on" if label == cur else ""
        return f'<button type="button" class="seg-btn{on}" data-period="{label}">{label}</button>'

    def _mode_btn(key, label, cur):
        on = " is-on" if key == cur else ""
        return f'<button type="button" class="seg-btn{on}" data-mode="{key}">{label}</button>'

    period_btns = "".join(_period_btn(p, default_period) for p in ("早", "中", "晚"))
    mode_btns = (
        _mode_btn("surf", "玩浪", default_mode)
        + _mode_btn("wind", "玩風", default_mode)
    )
    tip_esc = (
        daily_best["scoring_tip"]
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
    # Initial cards rendered server-side for default period/mode; JS refreshes on toggle
    day_card_parts = []
    for day in daily_best["dates"]:
        entry = ((daily_best["by"].get(day) or {}).get(default_period) or {}).get(default_mode) or {}
        best = entry.get("best")
        second = entry.get("second")
        label = daily_best["date_labels"].get(day, day)
        if not best:
            day_card_parts.append(
                f'    <div class="day-rec-card" data-day="{day}">'
                f'\n      <div class="ov-when">{label}</div>'
                f'\n      <div class="ov-name" style="color:var(--muted)">此時段無資料</div>'
                f"\n    </div>"
            )
            continue
        per = best.get("wave_per_s")
        per_s = f"{per:.0f}" if per is not None else "—"
        second_html = ""
        if second:
            second_html = (
                f'\n      <div class="ov-second">次選：{second["short"]} '
                f'{second["hour"]:02d}:00 · {second["wave_m"]:.1f}m / {second["wspd_kt"]:.0f} kt</div>'
            )
        day_card_parts.append(
            f'    <div class="day-rec-card" data-day="{day}" style="--accent:{best["accent"]}">'
            f'\n      <div class="ov-head"><span class="ov-when">{label}</span>'
            f'<span class="badge {best["badge_class"]}">{best["badge"]}</span></div>'
            f'\n      <div class="ov-name">{best["short"]}</div>'
            f'\n      <div class="ov-slot">{best["hour"]:02d}:00</div>'
            f'\n      <div class="ov-stats">'
            f'\n        <span>🌊 {best["wave_m"]:.1f}m / {per_s}s {best.get("wave_dir_zh") or ""}</span>'
            f'\n        <span>💨 {best["wspd_kt"]:.0f} kt {best.get("dir_zh") or ""}</span>'
            f"\n      </div>"
            f"{second_html}"
            f'\n      <div class="ov-tip">{best["tip"]}</div>'
            f"\n    </div>"
        )
    daily_rec_html = (
        '  <section class="daily-best" id="daily-best" aria-label="每日最佳推薦">\n'
        '    <div class="daily-best-bar">\n'
        f'      <div class="seg" role="group" aria-label="時段">{period_btns}</div>\n'
        f'      <div class="seg" role="group" aria-label="玩法">{mode_btns}</div>\n'
        "    </div>\n"
        f'    <p class="daily-best-tip">{tip_esc}</p>\n'
        '    <div class="overview daily-best-grid" id="daily-best-grid">\n'
        + "\n".join(day_card_parts)
        + "\n    </div>\n  </section>"
    )

    # Scatter detail table (full numbers; abbreviations live on SVG callouts)
    scatter_data = json.loads(Path("/workspace/wind-wave-scatter.json").read_text())
    short = {sp["key"]: sp["short"] for sp in SPOTS}
    rows = []

    def _period_cell(p, live=False):
        if p.get("period_s") is None:
            return "—"
        return f"{p['period_s']:.1f}"

    def _wind_cell(p):
        wd = p.get("wind_dir") or ""
        deg = p.get("wind_deg")
        return f"{wd} {deg:.0f}°" if deg is not None else (wd or "—")

    def _wave_cell(p):
        wd = p.get("wave_dir") or ""
        deg = p.get("wave_deg")
        return f"{wd} {deg:.0f}°" if deg is not None else (wd or "—")

    def _abbr_cell(p):
        a = p.get("abbr") or SCATTER_ABBR.get(p["name"]) or short.get(p["name"], p["name"])
        return a

    for p in scatter_data["forecast"]:
        name = short.get(p["name"], p.get("short") or p["name"])
        fx = p.get("x_raw", p["x"])
        fy = p.get("y_raw", p["y"])
        per = _period_cell(p, live=False)
        rows.append(
            f'<tr><td><span class="abbr">{_abbr_cell(p)}</span></td><td>{name}</td>'
            f'<td><span class="tag tag-fc">預報</span></td>'
            f"<td>{fx:.0f}</td><td>{fy:.1f}</td><td>{per}</td>"
            f"<td>{_wind_cell(p)}</td><td>{_wave_cell(p)}</td></tr>"
        )
    for p in scatter_data["live"]:
        live_label = p.get("short") or short.get(p["name"], p["name"])
        shared = ""
        if p.get("shared_for"):
            shared = f'（共用：{"／".join(p["shared_for"])}）'
        per = _period_cell(p, live=True)
        rows.append(
            f'<tr><td><span class="abbr">{_abbr_cell(p)}·即</span></td>'
            f"<td>{live_label}{shared}</td>"
            f'<td><span class="tag tag-live">即時</span></td>'
            f"<td>{p['x_raw']:.1f}</td><td>{p['y_raw']:.1f}</td>"
            f"<td>{per}</td>"
            f"<td>{_wind_cell(p)}</td><td>{_wave_cell(p)}</td></tr>"
        )

    scatter_legend_html = ""  # callouts are on-SVG; no external numbered legend

    # Time-axis slider data (multi-hour forecast JSON already in wind-wave-scatter.json)
    slider_slots = scatter_data.get("slider_hours") or [
        {"date": s["date"], "hour": s["hour"], "label": s["label"]} for s in scatter_data.get("slots") or []
    ]
    if not slider_slots and scatter_data.get("hour") is not None:
        slider_slots = [{"date": scatter_data.get("date") or TODAY, "hour": scatter_data["hour"],
                         "label": _slot_label(scatter_data.get("date") or TODAY, int(scatter_data["hour"]))}]
    default_idx = int(scatter_data.get("default_index") or 0)
    if default_idx < 0 or default_idx >= max(len(slider_slots), 1):
        default_idx = 0
    default_label = (slider_slots[default_idx]["label"] if slider_slots else f"{TODAY[5:].lstrip('0').replace('-', '/')} 15:00")
    day_sep_html, tick_html = _slider_day_marks(slider_slots)
    slider_max = max(len(slider_slots) - 1, 0)
    scatter_payload_js = json.dumps(scatter_data, ensure_ascii=False)


    # Sea state cards    # Sea state cards — 北海岸三點合為單一「富貴角」即時卡
    sea_cards = []
    north_card_done = False
    for sp in SPOTS:
        if sp["key"] in NORTH_COAST_SHARED_LIVE:
            if north_card_done:
                continue
            card_short = NORTH_COAST_LIVE_LABEL
            info = {}
            for nk in NORTH_COAST_SHARED_LIVE:
                raw = (cwa.get("spots") or {}).get(nk)
                if not raw and cwa.get("by_spot"):
                    r0 = cwa["by_spot"].get(nk) or {}
                    raw = {"buoy": r0.get("buoy") or {}, "coastal": r0.get("coastal") or {}, "note": r0.get("mapping_note") or ""}
                if raw and (raw.get("buoy") or {}).get("latest"):
                    info = raw
                    break
            if not info:
                raw = (cwa.get("spots") or {}).get(sp["key"]) or {}
                if not raw and cwa.get("by_spot"):
                    r0 = cwa["by_spot"].get(sp["key"]) or {}
                    raw = {"buoy": r0.get("buoy") or {}, "coastal": r0.get("coastal") or {}, "note": r0.get("mapping_note") or ""}
                info = raw or {}
            note = "北海岸三點即時共用富貴角浮標（只顯示一點）：中角／翡翠灣／石門婚紗 → C6AH2"
            north_card_done = True
        else:
            card_short = sp["short"]
            info = (cwa.get("spots") or {}).get(sp["key"]) or {}
            if not info and cwa.get("by_spot"):
                raw = cwa["by_spot"].get(sp["key"]) or {}
                info = {"buoy": raw.get("buoy") or {}, "coastal": raw.get("coastal") or {}, "note": raw.get("mapping_note") or ""}
            note = info.get("note") or ""

        buoy = info.get("buoy") or {}
        coastal = info.get("coastal") or {}
        bl = buoy.get("latest") or {}
        cl = coastal.get("latest") or {}
        bname = buoy.get("name_zh") or buoy.get("station_id") or "—"
        obs_t = (bl.get("time") or cl.get("time") or "")[:16].replace("T", " ")

        def fmt_wave(bl=bl):
            if bl.get("wave_height_m") is None:
                return "—"
            return f"{bl['wave_height_m']:.1f} m"

        def fmt_per(bl=bl):
            return f"{bl['wave_period_s']:.1f} s" if bl.get("wave_period_s") is not None else "—"

        def fmt_wdir(bl=bl):
            return bl.get("wave_dir") or "—"

        def fmt_temp(bl=bl):
            t = bl.get("sea_temp_c")
            return f"{t:.1f} °C" if t is not None else "—"

        wind_ms = bl.get("wind_speed_ms")
        wind_dir = bl.get("wind_dir")
        wind_src = "浮標"
        if wind_ms is None and cl.get("wind_speed_ms") is not None:
            wind_ms = cl["wind_speed_ms"]
            wind_dir = cl.get("wind_dir")
            wind_src = coastal.get("name_zh") or "沿岸"
        wind_s = f"{wind_ms:.1f} m/s {wind_dir or ''}（{wind_src}）" if wind_ms is not None else "—"

        sea_cards.append(f'''    <div class="sea-card">
      <div class="sea-top">
          <div class="sea-spot">{card_short}</div>
          <div class="sea-buoy">{bname} · {buoy.get("station_id","")}</div>
      </div>
      <div class="sea-grid">
        <div><span class="k">浪高</span><span class="v">{fmt_wave()}</span></div>
        <div><span class="k">週期</span><span class="v">{fmt_per()}</span></div>
        <div><span class="k">浪向</span><span class="v">{fmt_wdir()}</span></div>
        <div><span class="k">海溫</span><span class="v">{fmt_temp()}</span></div>
        <div class="wide"><span class="k">風</span><span class="v">{wind_s}</span></div>
      </div>
      <div class="sea-note">{note} · 觀測 {obs_t or "—"}</div>
    </div>''')

    # Spot sections
    spot_html = []
    for sp in SPOTS:
        sdata = forecast["spots"][sp["key"]]
        tdata = tides[sp["key"]]
        day_blocks = []
        for day in DAYS:
            slots = sdata["days"].get(day) or []
            rows_s = []
            for s in slots:
                wcls, hl = wind_class(s["wspd_kt"])
                tr_cls = f'slot {hl}'.strip()
                wdeg = s["dir_deg"]
                waved = s.get("wave_dir_deg")
                wave_rot = f'{waved:.0f}' if waved is not None else "0"
                rows_s.append(f'''        <tr class="{tr_cls}">
          <td class="t">{s["hour"]:02d}:00</td>
          <td class="wind">
            <span class="arrow" style="transform:rotate({wdeg}deg)">↓</span>
            <span class="wspd {wcls}">{s["wspd_kt"]:.0f} kt</span>
            <span class="wspd-ms">({s["wspd_ms"]:.1f} m/s)</span>
            <div class="sub">陣風 {s["gust_kt"]:.0f} kt · {s.get("dir_zh") or ""} {wdeg:.0f}°</div>
          </td>
          <td class="wave">
            <span class="arrow wave-a" style="transform:rotate({wave_rot}deg)">↓</span>
            <strong>{s["wave_m"]:.1f} m</strong> / {s.get("wave_per_s") or "—"}s
            <div class="sub">{s.get("wave_dir_zh") or ""} {wave_rot}°（{s.get("wave_dir") or ""}）</div>
          </td>
        </tr>''')
            # tides
            tevents = tdata["days"].get(day) or []
            tide_bits = []
            for e in tevents:
                tide_bits.append(f'<span class="tide-ev"><b>{e["type"]}</b> {e["time"]}（{e["height_cm"]:+d} cm）</span>')
            tide_html = " ".join(tide_bits) if tide_bits else "<span class='tide-ev'>（本日潮汐列較稀或尚無）</span>"
            day_blocks.append(f'''      <div class="day-block">
        <div class="day-title">{fmt_day_title(day)}</div>
        <table class="fc-table">
          <thead><tr><th>時間</th><th>風</th><th>浪</th></tr></thead>
          <tbody>
{"".join(rows_s)}</tbody>
        </table>
        <div class="tide-box">
          <div class="tide-label">潮汐 · {sp["tide_label"]}</div>
          <div class="tide-times">{tide_html}</div>
        </div>
      </div>''')

        sst = sdata.get("sst_c") or "—"
        spot_html.append(f'''  <section class="spot-card" id="spot-{sp["wg_id"]}">
    <header class="spot-head" style="--accent:{sp["accent"]}">
      <div>
        <h2>{sp["short"]}</h2>
        <p class="spot-sub">{sdata.get("name_wg") or sp["wg_name"]} · {sp["region"]}</p>
      </div>
      <div class="spot-meta">
        <a href="{sdata["url"]}" target="_blank" rel="noopener">Windguru {sp["wg_id"]}</a>
        <span>SST {sst}</span>
      </div>
    </header>
    <p class="caveat">{sp["caveat"]}</p>
    <div class="days-grid">
{"".join(day_blocks)}
    </div>
    <footer class="tide-src">潮位站：{tdata["station"]}（{tdata["station_code"]}）· 潮高為相對當地平均海平面 (cm) · {tdata.get("range_note","")} · <a href="{tdata["source"]}" target="_blank">CWA 來源</a></footer>
  </section>''')

    # Tide summary line for west
    def tide_summary(key):
        ev = tides[key]["days"].get(TODAY) or []
        low = next((e for e in ev if e["type"] == "乾潮"), None)
        high = None
        highs = [e for e in ev if e["type"] == "滿潮"]
        # afternoon high preferred
        for e in highs:
            if e["time"] >= "12:00":
                high = e
                break
        if not high and highs:
            high = highs[-1]
        return low, high

    hl_low, hl_high = tide_summary("後龍")
    sb_low, sb_high = tide_summary("松柏港")

    sim_index = load_similar_index()
    live_archive_html = render_live_archive_html(sim_index, TODAY)
    similar_panel_html = render_similar_panel_shell(sim_index)
    similar_js_const = similar_index_js_const(sim_index)
    similar_js_match = similar_match_js()

    html = f'''<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>衝浪預報對照 · 後龍／假日之森／松柏港／中角／翡翠灣／石門婚紗／無尾港／烏石</title>
<meta name="description" content="台灣八個浪點 Windguru GFS + 氣象署潮汐／浮標對照"/>
<link rel="preconnect" href="https://fonts.googleapis.com"/>
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin/>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;500;700;900&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet"/>
<style>{style}</style>
</head>
<body>
<div class="wrap">
  <header class="page-head">
      <h1>衝浪預報對照 · 後龍／假日之森／松柏港／中角／翡翠灣／石門婚紗／無尾港／烏石</h1>
      <p class="sub">Windguru GFS 13 km 預報 × 中央氣象署潮汐／浮標即時 · 台北時間</p>
      <p class="meta">預報擷取 {wg_fetched[:16].replace("T"," ")} · 浮標擷取 {cwa_fetched[:16].replace("T"," ")} · 模式 init {model_init}</p>
  </header>

  <h2 class="section">今日怎麼選</h2>
  <div class="pick-block pick-block-top">
    <p>{rec}</p>
    <p class="pick-tomorrow">{rec_tm_html}</p>
    <ul class="pick-notes">
      <li><strong>松柏港 vs 後龍／假日之森</strong>：同屬西岸 GFS 場；細節見下方據點卡。</li>
      <li><strong>西岸潮汐</strong>：後龍乾潮 {hl_low["time"] if hl_low else "—"}、滿潮 {hl_high["time"] if hl_high else "—"}；松柏港（大甲）乾潮 {sb_low["time"] if sb_low else "—"}、滿潮 {sb_high["time"] if sb_high else "—"}。</li>
      <li><strong>今日首選</strong>：{pick}（玩浪 · 午後邏輯）</li>
      <li><strong>明日早上六點</strong>：{pick_tm_line}</li>
    </ul>
  </div>

{daily_rec_html}
  <div class="legend">
    <span><i class="dot" style="background:var(--good)"></i>風速 &lt;6 kt 偏乾淨</span>
    <span><i class="dot" style="background:var(--ok)"></i>6–10 kt 中等</span>
    <span><i class="dot" style="background:#fb7185"></i>&gt;10 kt 浪面易亂</span>
    <span>上方可切 早／中／晚 · 玩浪／玩風</span>
    <span>箭頭＝風／浪去向（吹往／傳往）</span>
  </div>

{live_archive_html}
  <h2 class="section" id="wws-section-title">風速 × 浪高（{default_label}）</h2>
  <div class="scatter-block">
    <div class="scatter-head">
      <h3>散佈圖 · 預報圓點 ／ 即時菱形 · 點旁縮寫</h3>
      <p>X＝風速 (kt)、Y＝浪高 (m)；標記大小固定。圖上以色點＋<strong>點旁縮寫</strong>標示；完整數值見下方對照表。每點兩支箭頭：<strong style="color:#38bdf8">青＝風向</strong>、<strong style="color:#fbbf24">金＝浪向</strong>，皆為<strong>去向／吹往／傳往（flow to）</strong>（北風→朝南；北=0°、東=90°）。拖曳下方<strong>預報時間</strong>軸可切換時次（即時菱形固定）。</p>
    </div>
    <div class="scatter-svg-wrap">
{svg}
    </div>
    <div class="scatter-time" id="wws-time-ui">
      <div class="scatter-time-row">
        <label class="scatter-time-label" for="wws-time-range">預報時間</label>
        <span class="scatter-time-now" id="wws-time-label">{default_label}</span>
      </div>
      <div class="scatter-time-track-wrap">
        <div class="scatter-time-day-seps" aria-hidden="true">{day_sep_html}</div>
        <input type="range" id="wws-time-range" min="0" max="{slider_max}" step="1" value="{default_idx}"
               aria-valuemin="0" aria-valuemax="{slider_max}" aria-valuenow="{default_idx}"
               aria-label="預報時間" />
      </div>
      <div class="scatter-time-ticks" aria-hidden="true">{tick_html}</div>
    </div>
{similar_panel_html}
    <p class="scatter-cap" id="wws-cap">資料：Windguru GFS 預報（{default_label} 台北）＋ CWA 浮標即時（約 {cwa_fetched[:16].replace("T"," ")}）。縮寫：後龍、假森、松柏、中角、翡灣、石門、無尾、烏石、富貴（即時）。預報與即時座標接近時預報點會略偏移以免重疊。後龍／假日之森共用新竹浮標；<strong>北海岸三點即時共用富貴角浮標（只顯示一點）</strong>（中角／翡翠灣／石門婚紗 → 富貴角 C6AH2，預報圓點仍各自顯示）；無尾港→蘇澳資料浮標 46706A；烏石→龜山島浮標 46708A。綠帶&lt;8 kt、黃 8–14、紅 ≥15。</p>
    <details class="scatter-table">
      <summary>完整數值對照（含風向／浪向）</summary>
      <table>
        <thead><tr><th>縮寫</th><th>據點</th><th>來源</th><th>風速 kt</th><th>浪高 m</th><th>週期 s</th><th>風向</th><th>浪向</th></tr></thead>
        <tbody id="wws-table-body">
{"".join(rows)}
        </tbody>
      </table>
    </details>
  </div>

  <h2 class="section">即時海況（氣象署浮標）</h2>
  <div class="sea-block">
    <div class="sea-intro">
      <p>以下為<strong>中央氣象署浮標／潮位站實測</strong>（O-B0075-001），與上方 Windguru <strong>模式預報</strong>分開解讀。浮標在離岸處，岸邊浪高／風向可能不同；通訊延遲時欄位可能為「—」。北海岸三點即時共用富貴角浮標（只顯示一點）。</p>
      <p class="sea-fetched">浮標資料擷取：{cwa_fetched[:19].replace("T"," ")}（台北）</p>
    </div>
    <div class="sea-grid-cards">
{"".join(sea_cards)}
    </div>
    <p class="sea-links">
      <a href="https://www.cwa.gov.tw/V8/C/M/OBS_Marine.html" target="_blank" rel="noopener">即時海況頁</a> ·
      資料集 O-B0075-001
    </p>
  </div>

{"".join(spot_html)}

  <footer class="page-foot">
    風浪預報：Windguru GFS 13 km + GFS-Wave ·
    即時海況：中央氣象署浮標／潮位站 O-B0075-001（後龍／假日之森→新竹浮標 46757B；松柏港→臺中浮標 C6F01；北海岸三點即時共用富貴角浮標（只顯示一點）C6AH2；無尾港→蘇澳資料浮標 46706A；烏石→龜山島浮標 46708A）·
    潮汐預報：中央氣象署 F-A0021-001（相對當地平均海平面）·
    天文潮不含氣象增水 · 下水前請再對現場 · 預報擷取 {wg_fetched[:16].replace("T"," ")} · 浮標擷取 {cwa_fetched[:16].replace("T"," ")}（台北時間）
  </footer>
</div>
<script id="wws-scatter-data" type="application/json">{scatter_payload_js}</script>
<script id="daily-best-data" type="application/json">{daily_best_js}</script>
<script>
{similar_js_const}
{similar_js_match}
</script>
<script>
(function () {{
  var raw = document.getElementById("daily-best-data");
  var grid = document.getElementById("daily-best-grid");
  var root = document.getElementById("daily-best");
  if (raw && grid && root) {{
    var DB;
    try {{ DB = JSON.parse(raw.textContent); }} catch (e) {{ DB = null; }}
    if (DB) {{
      var period = DB.default_period || "中";
      var mode = DB.default_mode || "surf";
      function esc(s) {{
        return String(s == null ? "" : s)
          .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
          .replace(/"/g, "&quot;");
      }}
      function cardHtml(day) {{
        var label = (DB.date_labels && DB.date_labels[day]) || day;
        var entry = (((DB.by || {{}})[day] || {{}})[period] || {{}})[mode] || {{}};
        var best = entry.best;
        var second = entry.second;
        if (!best) {{
          return '<div class="day-rec-card" data-day="' + esc(day) + '">' +
            '<div class="ov-when">' + esc(label) + '</div>' +
            '<div class="ov-name" style="color:var(--muted)">此時段無資料</div></div>';
        }}
        var per = best.wave_per_s;
        var perS = (per == null || per !== per) ? "—" : String(Math.round(per));
        var secondHtml = "";
        if (second) {{
          secondHtml = '<div class="ov-second">次選：' + esc(second.short) + " " +
            String(second.hour).padStart(2, "0") + ":00 · " +
            (second.wave_m != null ? Number(second.wave_m).toFixed(1) : "—") + "m / " +
            (second.wspd_kt != null ? Math.round(second.wspd_kt) : "—") + " kt</div>";
        }}
        return '<div class="day-rec-card" data-day="' + esc(day) +
          '" style="--accent:' + esc(best.accent) + '">' +
          '<div class="ov-head"><span class="ov-when">' + esc(label) +
          '</span><span class="badge ' + esc(best.badge_class) + '">' + esc(best.badge) +
          '</span></div>' +
          '<div class="ov-name">' + esc(best.short) + '</div>' +
          '<div class="ov-slot">' + String(best.hour).padStart(2, "0") + ":00</div>" +
          '<div class="ov-stats">' +
          "<span>🌊 " + (best.wave_m != null ? Number(best.wave_m).toFixed(1) : "—") +
          "m / " + perS + "s " + esc(best.wave_dir_zh || "") + "</span>" +
          "<span>💨 " + (best.wspd_kt != null ? Math.round(best.wspd_kt) : "—") +
          " kt " + esc(best.dir_zh || "") + "</span></div>" +
          secondHtml +
          '<div class="ov-tip">' + esc(best.tip || "") + "</div></div>";
      }}
      function render() {{
        grid.innerHTML = (DB.dates || []).map(cardHtml).join("");
        root.querySelectorAll("[data-period]").forEach(function (b) {{
          b.classList.toggle("is-on", b.getAttribute("data-period") === period);
        }});
        root.querySelectorAll("[data-mode]").forEach(function (b) {{
          b.classList.toggle("is-on", b.getAttribute("data-mode") === mode);
        }});
      }}
      root.addEventListener("click", function (ev) {{
        var t = ev.target.closest("[data-period],[data-mode]");
        if (!t || !root.contains(t)) return;
        if (t.hasAttribute("data-period")) period = t.getAttribute("data-period");
        if (t.hasAttribute("data-mode")) mode = t.getAttribute("data-mode");
        render();
      }});
    }}
  }}
}})();
</script>
<script>
(function () {{
  var el = document.getElementById("wws-scatter-data");
  if (!el) return;
  var DATA;
  try {{ DATA = JSON.parse(el.textContent); }} catch (e) {{ return; }}
  var slots = DATA.slots || [];
  if (!slots.length) return;
  var axis = DATA.axis || {{}};
  var ox = axis.ox || 58, oy = axis.oy || 58, pw = axis.pw || 880, ph = axis.ph || 460;
  var xmin = axis.xmin, xmax = axis.xmax, ymin = axis.ymin, ymax = axis.ymax;
  var MR = axis.marker_r || 8, AL = axis.arrow_len || 40;
  var offsets = DATA.label_offsets || {{}};
  var today = DATA.today || "";
  var cwaAt = DATA.cwa_at || "";
  var range = document.getElementById("wws-time-range");
  var label = document.getElementById("wws-time-label");
  var title = document.getElementById("wws-title");
  var foot = document.getElementById("wws-foot");
  var cap = document.getElementById("wws-cap");
  var sec = document.getElementById("wws-section-title");
  var layer = document.getElementById("wws-forecast-layer");
  var tbody = document.getElementById("wws-table-body");
  if (!range || !layer) return;

  function xmap(x) {{ return ox + (x - xmin) / (xmax - xmin) * pw; }}
  function ymap(y) {{ return oy + ph - (y - ymin) / (ymax - ymin) * ph; }}
  function esc(s) {{
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }}
  function arrowLine(x, y, degFrom, color) {{
    if (degFrom == null || degFrom !== degFrom) return "";
    var flow = (degFrom + 180) % 360;
    var rad = flow * Math.PI / 180;
    var dx = Math.sin(rad) * AL, dy = -Math.cos(rad) * AL;
    var gap = 0.22;
    var x0 = x + dx * gap, y0 = y + dy * gap;
    var x1 = x + dx, y1 = y + dy;
    var mid = color.replace("#", "");
    return '<line x1="' + x0.toFixed(1) + '" y1="' + y0.toFixed(1) +
      '" x2="' + x1.toFixed(1) + '" y2="' + y1.toFixed(1) +
      '" stroke="' + color + '" stroke-width="2.4" marker-end="url(#arrow-' + mid + ')" />';
  }}
  function labelMarkup(p) {{
    var key = p.name + "|fc";
    var off = offsets[key] || [12, -10];
    var dx = off[0], dy = off[1];
    var px = xmap(p.x), py = ymap(p.y);
    var anchor = dx >= 0 ? "start" : "end";
    var lx = dx >= 0 ? px + MR + 6 : px - MR - 6;
    var ly = py + dy;
    var abbr = p.abbr || p.short || p.name;
    return '<text x="' + lx.toFixed(1) + '" y="' + ly.toFixed(1) +
      '" text-anchor="' + anchor + '" dominant-baseline="central" fill="' + esc(p.color) +
      '" font-size="11" font-weight="700" font-family="Noto Sans TC,system-ui,sans-serif" stroke="#0b1220" stroke-width="3" paint-order="stroke">' +
      esc(abbr) + "</text>";
  }}
  function pointMarkup(p) {{
    var x = xmap(p.x), y = ymap(p.y), r = MR;
    var html = "";
    if (p.wind_deg != null) html += arrowLine(x, y, p.wind_deg, "#38bdf8");
    if (p.wave_deg != null) html += arrowLine(x, y, p.wave_deg, "#fbbf24");
    html += '<circle cx="' + x.toFixed(1) + '" cy="' + y.toFixed(1) + '" r="' + r.toFixed(1) +
      '" fill="' + esc(p.color) + '" stroke="#fff" stroke-width="1.6" opacity="0.95"/>';
    return html;
  }}
  function titleText(slot) {{
    if (slot.date === today) return "今日 " + String(slot.hour).padStart(2, "0") + ":00 風速 × 浪高　預報 vs 即時浮標";
    return slot.label + " 風速 × 浪高　預報 vs 即時浮標";
  }}
  function windCell(p) {{
    var wd = p.wind_dir || "";
    if (p.wind_deg != null) return wd + " " + Math.round(p.wind_deg) + "°";
    return wd || "—";
  }}
  function waveCell(p) {{
    var wd = p.wave_dir || "";
    if (p.wave_deg != null) return wd + " " + Math.round(p.wave_deg) + "°";
    return wd || "—";
  }}
  function setSvgContent(el, html) {{
    // SVG <g>.innerHTML is unreliable across engines; parse via a wrapper <svg>.
    while (el.firstChild) el.removeChild(el.firstChild);
    if (!html) return;
    var wrap = document.createElement("div");
    wrap.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg">' + html + '</svg>';
    var root = wrap.firstChild;
    if (!root) return;
    while (root.firstChild) el.appendChild(root.firstChild);
  }}
  function updateTable(slot) {{
    if (!tbody) return;
    var live = DATA.live || [];
    var rows = [];
    (slot.forecast || []).forEach(function (p) {{
      var fx = p.x_raw != null ? p.x_raw : p.x;
      var fy = p.y_raw != null ? p.y_raw : p.y;
      var per = p.period_s != null ? p.period_s.toFixed(1) : "—";
      rows.push('<tr><td><span class="abbr">' + esc(p.abbr || "") + "</span></td><td>" +
        esc(p.short || p.name) + '</td><td><span class="tag tag-fc">預報</span></td><td>' +
        Math.round(fx) + "</td><td>" + Number(fy).toFixed(1) + "</td><td>" + per +
        "</td><td>" + esc(windCell(p)) + "</td><td>" + esc(waveCell(p)) + "</td></tr>");
    }});
    live.forEach(function (p) {{
      var shared = "";
      if (p.shared_for && p.shared_for.length) shared = "（共用：" + p.shared_for.join("／") + "）";
      var per = p.period_s != null ? p.period_s.toFixed(1) : "—";
      rows.push('<tr><td><span class="abbr">' + esc(p.abbr || "") + "·即</span></td><td>" +
        esc(p.short || p.name) + shared + '</td><td><span class="tag tag-live">即時</span></td><td>' +
        Number(p.x_raw).toFixed(1) + "</td><td>" + Number(p.y_raw).toFixed(1) + "</td><td>" + per +
        "</td><td>" + esc(windCell(p)) + "</td><td>" + esc(waveCell(p)) + "</td></tr>");
    }});
    tbody.innerHTML = rows.join("");
  }}
  function apply(idx) {{
    idx = Math.max(0, Math.min(slots.length - 1, idx | 0));
    var slot = slots[idx];
    var html = "";
    (slot.forecast || []).forEach(function (p) {{ html += pointMarkup(p); }});
    (slot.forecast || []).forEach(function (p) {{ html += labelMarkup(p); }});
    setSvgContent(layer, html);
    if (label) label.textContent = slot.label;
    if (title) title.textContent = titleText(slot);
    if (foot) {{
      foot.textContent = "預報 " + slot.label + " 台北｜即時約 " + cwaAt +
        "｜北海岸三點即時共用富貴角（只顯示一點）｜後龍／假日之森共用新竹略偏移｜綠<8kt／黃8–14／紅≥15";
    }}
    if (cap) {{
      cap.innerHTML = "資料：Windguru GFS 預報（" + esc(slot.label) +
        " 台北）＋ CWA 浮標即時（約 " + esc(cwaAt) +
        "）。縮寫：後龍、假森、松柏、中角、翡灣、石門、無尾、烏石、富貴（即時）。預報與即時座標接近時預報點會略偏移以免重疊。後龍／假日之森共用新竹浮標；<strong>北海岸三點即時共用富貴角浮標（只顯示一點）</strong>（中角／翡翠灣／石門婚紗 → 富貴角 C6AH2，預報圓點仍各自顯示）；無尾港→蘇澳資料浮標 46706A；烏石→龜山島浮標 46708A。綠帶&lt;8 kt、黃 8–14、紅 ≥15。";
    }}
    if (sec) sec.textContent = "風速 × 浪高（" + slot.label + "）";
    range.value = String(idx);
    range.setAttribute("aria-valuenow", String(idx));
    updateTable(slot);
    if (window.__updateSimilarArchive) window.__updateSimilarArchive(slot);
  }}
  function onInput() {{ apply(parseInt(range.value, 10) || 0); }}
  range.addEventListener("input", onInput);
  range.addEventListener("change", onInput);
  var start = typeof DATA.default_index === "number" ? DATA.default_index : 0;
  apply(start);
}})();
</script>
</body>
</html>
'''
    return html


def write_tldr(forecast, tides, cwa, wg_fetched, cwa_fetched, pick, rec, pick_tm=None, rec_tm=None):
    lines = [
        f"# 衝浪速覽 · {datetime.strptime(DAYS[0], '%Y-%m-%d').month}/{datetime.strptime(DAYS[0], '%Y-%m-%d').day}–{datetime.strptime(DAYS[-1], '%Y-%m-%d').month}/{datetime.strptime(DAYS[-1], '%Y-%m-%d').day}（據點｜台北時間）",
        "",
        f"擷取：{wg_fetched[:16].replace('T',' ')}（台北時間）｜模式：GFS 13 km",
        "",
        "## 今天開哪？",
        f"- **今日首選 → {pick}**",
        f"- **明日早上六點 → {pick_tm or '—'}**",
        *( [f"- {rec_tm}"] if rec_tm else [] ),
        f"- {rec}",
        "",
        "## 潮汐提示（CWA F-A0021-001）",
        "| 據點 | 潮位站 | 今日乾潮 | 今日午後滿潮 |",
        "|---|---|---|---|",
    ]
    for sp in SPOTS:
        t = tides[sp["key"]]
        ev = t["days"].get(TODAY) or []
        lows = [e for e in ev if e["type"] == "乾潮"]
        highs = [e for e in ev if e["type"] == "滿潮" and e["time"] >= "12:00"]
        low_s = "／".join(f"{e['time']}（{e['height_cm']} cm）" for e in lows) or "—"
        high_s = "／".join(f"{e['time']}（+{e['height_cm']} cm）" for e in highs) or "—"
        lines.append(f"| {sp['short']} | {t.get('location_name') or sp['tide_label']} | {low_s} | {high_s} |")

    lines += [
        "",
        "## 即時海況（CWA 浮標 O-B0075-001）",
        f"擷取：{cwa_fetched[:16].replace('T',' ')}（台北時間）｜實測 ≠ Windguru 預報",
        "",
        "| 據點 | 浮標 | 浪高 | 週期 | 浪向 | 海溫 | 浮標風 |",
        "|---|---|---|---|---|---|---|",
    ]
    north_tldr_done = False
    for sp in SPOTS:
        if sp["key"] in NORTH_COAST_SHARED_LIVE:
            if north_tldr_done:
                continue
            label = NORTH_COAST_LIVE_LABEL
            info = {}
            for nk in NORTH_COAST_SHARED_LIVE:
                raw = (cwa.get("spots") or {}).get(nk)
                if not raw and cwa.get("by_spot"):
                    r0 = cwa["by_spot"].get(nk) or {}
                    raw = {"buoy": r0.get("buoy") or {}, "coastal": r0.get("coastal") or {}, "note": r0.get("mapping_note") or ""}
                if raw and (raw.get("buoy") or {}).get("latest"):
                    info = raw
                    break
            if not info and cwa.get("by_spot"):
                r0 = cwa["by_spot"].get(sp["key"]) or {}
                info = {"buoy": r0.get("buoy") or {}, "coastal": r0.get("coastal") or {}}
            north_tldr_done = True
        else:
            label = sp["short"]
            info = (cwa.get("spots") or {}).get(sp["key"]) or {}
            if not info and cwa.get("by_spot"):
                raw = cwa["by_spot"].get(sp["key"]) or {}
                info = {"buoy": raw.get("buoy") or {}, "coastal": raw.get("coastal") or {}, "note": raw.get("mapping_note") or ""}
        buoy = info.get("buoy") or {}
        bl = buoy.get("latest") or {}
        coastal = (info.get("coastal") or {}).get("latest") or {}
        wind_ms = bl.get("wind_speed_ms")
        wind_dir = bl.get("wind_dir")
        if wind_ms is None:
            wind_ms = coastal.get("wind_speed_ms")
            wind_dir = coastal.get("wind_dir")
        wh = f"{bl['wave_height_m']:.1f} m" if bl.get("wave_height_m") is not None else "—"
        wp = f"{bl['wave_period_s']:.1f} s" if bl.get("wave_period_s") is not None else "—"
        st = f"{bl['sea_temp_c']:.1f} °C" if bl.get("sea_temp_c") is not None else "—"
        wf = f"{wind_ms:.1f} m/s {wind_dir or ''}" if wind_ms is not None else "—"
        lines.append(
            f"| {label} | {buoy.get('name_zh','')} {buoy.get('station_id','')} | {wh} | {wp} | {bl.get('wave_dir') or '—'} | {st} | {wf} |"
        )

    lines += [
        "",
        "## 風速×浪高散佈圖",
        "- 預設今日 **15:00** 台北；頁面下方有「預報時間」滑桿可切換今日白天＋隔日清晨時次。",
        "- X=風速(kt)、Y=浪高(m)；青箭＝風向去向、金箭＝浪向去向（flow to）。",
        "- 圓點＝Windguru 預報（隨滑桿更新）；菱形＝CWA 浮標即時（固定）；點旁縮寫；完整數值見對照表。",
        "- 縮寫：後龍、假森、松柏、中角、翡灣、石門、無尾、烏石、富貴（即時）。",
        "- 北海岸三點即時共用富貴角浮標（只顯示一點）；中角／翡翠灣／石門婚紗預報圓點仍各自保留。",
        "",
        "詳細對照：`/workspace/surf-forecast.html`",
        "",
    ]
    Path("/workspace/surf-tldr.md").write_text("\n".join(lines), encoding="utf-8")


def rebuild_html_from_cache():
    """Rebuild HTML/SVG from cached Windguru + CWA JSON (no remote fetches)."""
    print("=== HTML-only rebuild from cache ===")
    forecast = json.loads(Path("/workspace/tide-data/forecast_slots.json").read_text(encoding="utf-8"))
    tides = json.loads(Path("/workspace/tide-data/tides.json").read_text(encoding="utf-8"))
    cwa = json.loads(Path("/workspace/cwa-sea-state.json").read_text(encoding="utf-8"))
    wg_fetched = forecast.get("fetched_at") or now_taipei().isoformat()
    cwa_fetched = cwa.get("fetched_at") or now_taipei().isoformat()
    model_init = next(iter(forecast["spots"].values())).get("model_init", "")
    ensure_similar_archive_assets()
    svg, scatter_json = render_scatter_svg(forecast, cwa, 15)
    Path("/workspace/wind-wave-scatter.svg").write_text(svg, encoding="utf-8")
    Path("/workspace/wind-wave-scatter.json").write_text(
        json.dumps(scatter_json, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    pick, rec = pick_today_recommendation(forecast, tides)
    pick_tm, rec_tm = pick_tomorrow_morning_recommendation(forecast)
    print("今日首選:", pick)
    print("明日早上:", pick_tm, rec_tm)
    print(rec)
    html = build_html(forecast, tides, cwa, svg, wg_fetched, cwa_fetched, pick, rec, pick_tm, rec_tm)
    Path("/workspace/surf-forecast.html").write_text(html, encoding="utf-8")
    repo = Path("/workspace/surf-forecast-repo")
    if repo.is_dir():
        (repo / "index.html").write_text(html, encoding="utf-8")
        (repo / "wind-wave-scatter.svg").write_bytes(Path("/workspace/wind-wave-scatter.svg").read_bytes())
    write_tldr(forecast, tides, cwa, wg_fetched, cwa_fetched, pick, rec, pick_tm, rec_tm)
    summary = {
        "mode": "html-only",
        "wg_fetched_at": wg_fetched,
        "cwa_fetched_at": cwa_fetched,
        "model_init": model_init,
        "今日首選": pick,
        "recommendation": rec,
        "明日早上首選": pick_tm,
        "明日早上推薦": rec_tm,
        "daily_best_dates": compute_daily_best(forecast, TODAY)["dates"],
        "default_period": default_period_for_now(),
    }
    Path("/workspace/refresh-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("DONE", json.dumps(summary, ensure_ascii=False))
    return summary


def main():
    print("=== 1) Windguru ===")
    forecast, raw, wg_fetched, model_init = fetch_all_windguru()
    print("fetched_at", wg_fetched, "init", model_init)

    print("=== 2) CWA tides ===")
    tides, tide_fetched = fetch_tides()
    forecast["tides"] = {k: {kk: vv for kk, vv in v.items() if kk != "fetched_at"} for k, v in tides.items()}
    # Keep tides also nested like before under forecast_slots
    Path("/workspace/tide-data/forecast_slots.json").write_text(
        json.dumps(forecast, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    Path("/workspace/tide-data/tides.json").write_text(
        json.dumps(tides, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    Path("/workspace/windguru-raw.json").write_text(
        json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("=== 3) CWA sea state ===")
    subprocess.check_call(["python3", "/workspace/fetch_cwa_sea_state.py"])
    cwa = json.loads(Path("/workspace/cwa-sea-state.json").read_text(encoding="utf-8"))
    cwa_fetched = cwa.get("fetched_at") or now_taipei().isoformat()

    print("=== 3.5) Similar archive index ===")
    ensure_similar_archive_assets()

    print("=== 4) Scatter SVG ===")
    svg, scatter_json = render_scatter_svg(forecast, cwa, 15)
    Path("/workspace/wind-wave-scatter.svg").write_text(svg, encoding="utf-8")
    Path("/workspace/wind-wave-scatter.json").write_text(
        json.dumps(scatter_json, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    pick, rec = pick_today_recommendation(forecast, tides)
    pick_tm, rec_tm = pick_tomorrow_morning_recommendation(forecast)
    print("今日首選:", pick)
    print("明日早上:", pick_tm, rec_tm)
    print(rec)

    print("=== 5) HTML ===")
    html = build_html(forecast, tides, cwa, svg, wg_fetched, cwa_fetched, pick, rec, pick_tm, rec_tm)
    Path("/workspace/surf-forecast.html").write_text(html, encoding="utf-8")
    # Mirror to GitHub Pages repo working tree
    repo = Path("/workspace/surf-forecast-repo")
    if repo.is_dir():
        (repo / "index.html").write_text(html, encoding="utf-8")
        svg_src = Path("/workspace/wind-wave-scatter.svg")
        if svg_src.exists():
            (repo / "wind-wave-scatter.svg").write_bytes(svg_src.read_bytes())
        # archive thumbs + index already written by ensure_similar_archive_assets
    write_tldr(forecast, tides, cwa, wg_fetched, cwa_fetched, pick, rec, pick_tm, rec_tm)

    # Also try matplotlib script (optional; page uses custom SVG)
    try:
        subprocess.check_call(["python3", "/workspace/make_wind_wave_scatter.py"], cwd="/workspace")
        # restore custom SVG as page source of truth
        Path("/workspace/wind-wave-scatter.svg").write_text(svg, encoding="utf-8")
        Path("/workspace/wind-wave-scatter.json").write_text(
            json.dumps(scatter_json, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception as e:
        print("matplotlib scatter optional fail:", e)

    summary = {
        "wg_fetched_at": wg_fetched,
        "tide_fetched_at": tide_fetched,
        "cwa_fetched_at": cwa_fetched,
        "model_init": model_init,
        "今日首選": pick,
        "recommendation": rec,
        "明日早上首選": pick_tm,
        "明日早上推薦": rec_tm,
    }
    Path("/workspace/refresh-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("DONE", json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    if any(a in ("--html-only", "--from-cache", "--rebuild-html") for a in sys.argv[1:]):
        rebuild_html_from_cache()
    else:
        main()
