#!/usr/bin/env python3
"""阿浪 archive UI helpers for refresh_surf_forecast.py."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

ARCHIVE_ROOT = Path("/workspace/surf-archive")
REPO_ARCHIVE = Path("/workspace/surf-forecast-repo/archive")
LOCAL_ARCHIVE = Path("/workspace/archive")

ARCHIVE_SLUG_TO_SPOT = {
    "zhongjiao": "中角",
    "wuwei": "無尾港",
    "zhunan": "竹南假日之森",
}
ARCHIVE_SPOT_TO_SLUG = {v: k for k, v in ARCHIVE_SLUG_TO_SPOT.items()}

ARCHIVE_CSS = """
/* archive-live-css */
.archive-live { margin: 18px 0 8px; }
.archive-intro, .archive-empty { color: var(--muted, #8b9bb4); font-size: 0.88rem; margin: 0 0 12px; }
.archive-grid, .similar-grid {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px;
}
.archive-card, .similar-card {
  background: rgba(15, 23, 42, 0.65); border: 1px solid var(--line, #1e3a5f);
  border-radius: 14px; overflow: hidden; display: flex; flex-direction: column;
}
.archive-thumb, .similar-thumb, video.archive-thumb, video.similar-thumb {
  width: 100%; aspect-ratio: 16/10; object-fit: cover; display: block; background: #0b1220;
}

video.similar-thumb {
  display: block; width: 100%; aspect-ratio: 16 / 9; object-fit: cover;
  background: #0b1220; cursor: pointer;
}
.archive-media, .similar-media { position: relative; display: block; cursor: pointer; }
.archive-media:hover .archive-play-hint,
.similar-media:hover .similar-play-hint { opacity: 0; }
.archive-play-hint, .similar-play-hint { transition: opacity .15s ease; }
.similar-media:hover .similar-play-hint { opacity: 0; }
.similar-play-hint { transition: opacity .15s ease; }
.archive-play-hint, .similar-play-hint {
  position: absolute; right: 8px; bottom: 8px; font-size: 0.7rem;
  background: rgba(0,0,0,0.55); color: #e8eef7; padding: 2px 8px; border-radius: 999px;
  pointer-events: none;
}
.archive-body, .similar-body { padding: 10px 12px 12px; }
.archive-spot, .similar-spot { font-weight: 700; font-size: 0.95rem; color: var(--text, #e8eef7); }
.archive-meta, .similar-meta { font-size: 0.72rem; color: var(--muted, #8b9bb4); margin-top: 2px; }
.archive-notes, .similar-notes {
  margin: 8px 0; font-size: 0.8rem; color: #cbd5e1; line-height: 1.45;
  display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden;
}
.archive-drive, .similar-drive {
  font-size: 0.75rem; color: #7dd3fc; text-decoration: none; font-weight: 600;
}
.archive-drive:hover, .similar-drive:hover { text-decoration: underline; }
.similar-panel {
  margin: 14px 0 4px; padding: 12px 14px; border-radius: 12px;
  background: rgba(15, 23, 42, 0.45); border: 1px solid var(--line, #1e3a5f);
}
.similar-head h3 { margin: 0 0 4px; font-size: 0.95rem; color: var(--text, #e8eef7); }
.similar-head p { margin: 0; font-size: 0.8rem; color: var(--muted, #8b9bb4); }
.similar-note { margin: 8px 0 10px; font-size: 0.78rem; color: #fbbf24; }
.similar-badge {
  display: inline-block; margin-top: 4px; padding: 1px 8px; border-radius: 999px;
  font-size: 0.68rem; font-weight: 700; color: #7dd3fc; border: 1px solid rgba(125,211,252,.45);
}
.similar-empty { color: var(--muted, #8b9bb4); font-size: 0.8rem; grid-column: 1 / -1; }
@media (max-width: 560px) {
  .archive-grid, .similar-grid { grid-template-columns: 1fr; }
}

.clip-lightbox {
  position: fixed; inset: 0; z-index: 9999;
  display: flex; align-items: center; justify-content: center;
  background: rgba(2, 8, 20, 0.78); backdrop-filter: blur(4px);
  padding: 24px 16px; box-sizing: border-box;
}
.clip-lightbox[hidden] { display: none !important; }
.clip-lightbox-panel {
  position: relative; width: min(960px, 100%);
  background: #0b1220; border-radius: 14px; overflow: hidden;
  border: 1px solid rgba(125,211,252,.25);
  box-shadow: 0 24px 60px rgba(0,0,0,.55);
}
.clip-lightbox-panel video {
  display: block; width: 100%; max-height: min(78vh, 720px);
  background: #000; object-fit: contain;
}
.clip-lightbox-cap {
  padding: 10px 14px 12px; color: #e8eef7; font-size: 0.9rem;
  display: flex; justify-content: space-between; gap: 12px; align-items: center;
}
.clip-lightbox-cap span { color: #8b9bb4; font-size: 0.78rem; }
.clip-lightbox-close {
  position: absolute; top: 8px; right: 10px; z-index: 2;
  width: 36px; height: 36px; border-radius: 999px; border: 0;
  background: rgba(0,0,0,.55); color: #fff; font-size: 1.25rem; cursor: pointer;
  line-height: 1;
}
.clip-lightbox-close:hover { background: rgba(0,0,0,.75); }
/* /archive-live-css */
"""


def load_similar_index():
    p = ARCHIVE_ROOT / "similar-index.json"
    if not p.exists():
        return {"entries": [], "note_zh": "", "archive_spots": list(ARCHIVE_SLUG_TO_SPOT), "spot_map": ARCHIVE_SLUG_TO_SPOT}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"entries": [], "note_zh": "", "archive_spots": list(ARCHIVE_SLUG_TO_SPOT), "spot_map": ARCHIVE_SLUG_TO_SPOT}


def ensure_similar_archive_assets():
    """Rebuild similar-index + thumbs; mirror into repo + /workspace/archive."""
    try:
        subprocess.check_call(["python3", "/workspace/build_similar_index.py"])
    except Exception as e:
        print("build_similar_index fail:", e)
    idx = load_similar_index()
    REPO_ARCHIVE.mkdir(parents=True, exist_ok=True)
    src_idx = ARCHIVE_ROOT / "similar-index.json"
    if src_idx.exists():
        text = src_idx.read_text(encoding="utf-8")
        (REPO_ARCHIVE / "similar-index.json").write_text(text, encoding="utf-8")
        LOCAL_ARCHIVE.mkdir(parents=True, exist_ok=True)
        (LOCAL_ARCHIVE / "similar-index.json").write_text(text, encoding="utf-8")
        for e in idx.get("entries") or []:
            thumb = e.get("thumb") or ""
            rel = thumb[len("archive/") :] if thumb.startswith("archive/") else thumb
            src = REPO_ARCHIVE / rel
            if src.exists():
                dest = LOCAL_ARCHIVE / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(src.read_bytes())
    return idx


def render_live_archive_html(sim_index, today: str) -> str:
    entries = [e for e in (sim_index.get("entries") or []) if e.get("date") == today]
    order = ["zhongjiao", "wuwei", "zhunan"]
    # One card per spot: prefer latest captured_at when multiple runs exist
    by_slug = {}
    for e in entries:
        slug = e.get("slug")
        if slug not in by_slug or (e.get("captured_at") or "") > (by_slug[slug].get("captured_at") or ""):
            by_slug[slug] = e
    ordered = [by_slug[s] for s in order if s in by_slug]
    if not ordered:
        return (
            '  <section class="archive-live" id="archive-live">\n'
            '    <h2 class="section">今日實況</h2>\n'
            '    <p class="archive-empty">尚無今日直播採集</p>\n'
            "  </section>\n"
        )
    cards = []
    for e in ordered:
        notes = (e.get("wave_notes_zh") or "").strip()
        short = notes if len(notes) <= 90 else notes[:88] + "…"
        cap = (e.get("captured_at") or "")[:16].replace("T", " ")
        cond = e.get("conditions") or {}
        cond_bits = []
        if cond.get("wave_m") is not None:
            cond_bits.append(f'浪 {float(cond["wave_m"]):.1f}m')
        if cond.get("wave_per_s") is not None:
            cond_bits.append(f'{float(cond["wave_per_s"]):.0f}s')
        if cond.get("wspd_kt") is not None:
            cond_bits.append(f'風 {float(cond["wspd_kt"]):.0f}kt')
        cond_line = " · ".join(cond_bits)
        thumb = e.get("thumb") or ""
        clip = e.get("clip") or ""
        spot = e.get("spot") or e.get("slug")
        meta = cap + ((" · " + cond_line) if cond_line else "")
        if clip:
            media = (
                '      <div class="archive-media">\n'
                f'        <video class="archive-thumb" muted playsinline loop preload="metadata" '
                f'poster="./{thumb}" src="./{clip}" title="{spot} 實況（移上播放 · 點擊放大）"></video>\n'
                '        <span class="archive-play-hint">移上播放 · 點擊放大</span>\n'
                "      </div>\n"
            )
        else:
            media = f'      <img class="archive-thumb" src="./{thumb}" alt="{spot} 實況" loading="lazy"/>\n'
        cards.append(
            "    <article class=\"archive-card\">\n"
            + media
            + '      <div class="archive-body">\n'
            f'        <div class="archive-spot">{spot}</div>\n'
            f'        <div class="archive-meta">{meta}</div>\n'
            f'        <p class="archive-notes">{short}</p>\n'
            "      </div>\n"
            "    </article>"
        )
    return (
        '  <section class="archive-live" id="archive-live">\n'
        '    <h2 class="section">今日實況</h2>\n'
        '    <p class="archive-intro">阿浪直播截幀＋目視筆記（中角／無尾港／竹南假日之森）。</p>\n'
        '    <div class="archive-grid">\n'
        + "\n".join(cards)
        + "\n    </div>\n  </section>\n"
    )


def render_similar_panel_shell(sim_index) -> str:
    dates = {e.get("date") for e in (sim_index.get("entries") or [])}
    note = sim_index.get("note_zh") or ""
    if len(dates) <= 1:
        note = note or "歷史樣本尚少，僅供參考"
    if note:
        note_html = f'<p class="similar-note" id="similar-note">{note}</p>'
    else:
        note_html = '<p class="similar-note" id="similar-note" hidden></p>'
    return (
        '    <div class="similar-panel" id="similar-panel">\n'
        '      <div class="similar-head">\n'
        "        <h3>類似浪況</h3>\n"
        "        <p>依目前滑桿時次的 Windguru 風／浪，從歷史直播檔找最接近的實況（中角／無尾港／假日之森）。</p>\n"
        "      </div>\n"
        f"      {note_html}\n"
        '      <div class="similar-grid" id="similar-grid"></div>\n'
        "    </div>\n"
    )


def similar_index_js_const(sim_index) -> str:
    payload = json.dumps(sim_index, ensure_ascii=False)
    return f"const SIMILAR_INDEX = {payload};\n"


def similar_match_js() -> str:
    """Client-side nearest-neighbor matching + panel update (hooked from slider apply)."""
    return r"""
(function () {
  var SPOT_ORDER = ["zhongjiao", "wuwei", "zhunan"];
  var SPOT_NAME = (SIMILAR_INDEX && SIMILAR_INDEX.spot_map) || {
    zhongjiao: "中角", wuwei: "無尾港", zhunan: "竹南假日之森"
  };
  var NAME_TO_SLUG = {};
  Object.keys(SPOT_NAME).forEach(function (slug) { NAME_TO_SLUG[SPOT_NAME[slug]] = slug; });
  // also accept short labels
  NAME_TO_SLUG["假日之森"] = "zhunan";

  function circDist(a, b) {
    if (a == null || b == null || isNaN(a) || isNaN(b)) return null;
    var d = Math.abs(a - b) % 360;
    return d > 180 ? 360 - d : d;
  }
  function distEntry(query, entry) {
    var c = entry.conditions || {};
    var wWave = 3.0, wWind = 2.5, wPer = 1.5, wDir = 0.8, wWdir = 0.8;
    var acc = 0, wsum = 0;
    function add(diff, scale, w) {
      if (diff == null || isNaN(diff)) return;
      var n = diff / scale;
      acc += w * n * n;
      wsum += w;
    }
    if (query.wave_m != null && c.wave_m != null) add(Math.abs(query.wave_m - c.wave_m), 2.0, wWave);
    if (query.wspd_kt != null && c.wspd_kt != null) add(Math.abs(query.wspd_kt - c.wspd_kt), 20.0, wWind);
    if (query.wave_per_s != null && c.wave_per_s != null) add(Math.abs(query.wave_per_s - c.wave_per_s), 12.0, wPer);
    var cd = circDist(query.dir_deg, c.dir_deg);
    if (cd != null) add(cd, 180.0, wDir);
    var cwd = circDist(query.wave_dir_deg, c.wave_dir_deg);
    if (cwd != null) add(cwd, 180.0, wWdir);
    if (wsum <= 0) return 9e9;
    return Math.sqrt(acc / wsum);
  }
  function similarityPct(d) {
    // d~0 → 100%; d~1 → ~0%
    var pct = Math.round(100 * Math.max(0, 1 - d));
    return Math.max(0, Math.min(100, pct));
  }
  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }
  function queryFromSlot(slot, spotName) {
    var pts = (slot && slot.forecast) || [];
    var p = null;
    for (var i = 0; i < pts.length; i++) {
      if (pts[i].name === spotName) { p = pts[i]; break; }
    }
    if (!p) return null;
    return {
      wspd_kt: p.x_raw != null ? p.x_raw : p.x,
      wave_m: p.y_raw != null ? p.y_raw : p.y,
      wave_per_s: p.period_s,
      dir_deg: p.wind_deg,
      wave_dir_deg: p.wave_deg
    };
  }
  function bestMatch(slug, query) {
    var entries = (SIMILAR_INDEX && SIMILAR_INDEX.entries) || [];
    var best = null, bestD = 9e9;
    for (var i = 0; i < entries.length; i++) {
      var e = entries[i];
      if (e.slug !== slug) continue;
      if (!e.conditions) continue;
      var d = distEntry(query, e);
      if (d < bestD) { bestD = d; best = e; }
    }
    // if no conditions, still allow any entry for slug
    if (!best) {
      for (var j = 0; j < entries.length; j++) {
        if (entries[j].slug === slug) { best = entries[j]; bestD = 1; break; }
      }
    }
    return best ? { entry: best, dist: bestD, pct: similarityPct(bestD) } : null;
  }
  function renderSimilar(slot) {
    var grid = document.getElementById("similar-grid");
    if (!grid) return;
    var html = [];
    SPOT_ORDER.forEach(function (slug) {
      var name = SPOT_NAME[slug];
      var q = queryFromSlot(slot, name);
      if (!q) {
        html.push('<div class="similar-card"><div class="similar-body"><div class="similar-spot">' +
          esc(name) + '</div><p class="similar-empty">此預報時次無該點資料</p></div></div>');
        return;
      }
      var m = bestMatch(slug, q);
      if (!m) {
        html.push('<div class="similar-card"><div class="similar-body"><div class="similar-spot">' +
          esc(name) + '</div><p class="similar-empty">尚無歷史樣本</p></div></div>');
        return;
      }
      var e = m.entry;
      var notes = (e.wave_notes_zh || "").trim();
      if (notes.length > 80) notes = notes.slice(0, 78) + "…";
      var label = m.pct >= 70 ? ("相近 " + m.pct + "%") : (m.pct >= 40 ? ("接近 " + m.pct + "%") : ("參考 " + m.pct + "%"));
      var media;
      if (e.clip) {
        media =
          '<div class="similar-media">' +
            '<video class="similar-thumb" muted playsinline loop preload="metadata" ' +
              'poster="./' + esc(e.thumb || "") + '" src="./' + esc(e.clip) + '" ' +
              'title="' + esc(e.spot || name) + '（移上播放 · 點擊放大）"></video>' +
            '<span class="similar-play-hint">移上播放 · 點擊放大</span>' +
          '</div>';
      } else {
        media =
          '<img class="similar-thumb" src="./' + esc(e.thumb || "") + '" alt="' + esc(e.spot || name) + '" loading="lazy"/>';
      }
      html.push(
        '<article class="similar-card">' +
          media +
          '<div class="similar-body">' +
            '<div class="similar-spot">' + esc(e.spot || name) + "</div>" +
            '<div class="similar-meta">' + esc(e.date || "") +
              (e.captured_at ? (" · " + esc(String(e.captured_at).slice(11, 16))) : "") + "</div>" +
            '<span class="similar-badge">' + esc(label) + "</span>" +
            '<p class="similar-notes">' + esc(notes) + "</p>" +
          "</div></article>"
      );
    });
    if (!html.length) {
      grid.innerHTML = '<p class="similar-empty">尚無歷史樣本</p>';
    } else {
      grid.innerHTML = html.join("");
      bindHoverPlay(grid);
    }
  }
  function pauseAllArchiveVideos(except) {
    document.querySelectorAll("#archive-live video, #similar-grid video").forEach(function (v) {
      if (except && v === except) return;
      try { v.pause(); v.currentTime = 0; } catch (e) {}
    });
  }
  function ensureLightbox() {
    var box = document.getElementById("clip-lightbox");
    if (box) return box;
    box = document.createElement("div");
    box.id = "clip-lightbox";
    box.className = "clip-lightbox";
    box.hidden = true;
    box.innerHTML =
      '<div class="clip-lightbox-panel" role="dialog" aria-modal="true">' +
        '<button type="button" class="clip-lightbox-close" aria-label="關閉">×</button>' +
        '<video controls playsinline preload="metadata"></video>' +
        '<div class="clip-lightbox-cap"><strong id="clip-lightbox-title"></strong><span>Esc / 點背景關閉</span></div>' +
      '</div>';
    document.body.appendChild(box);
    var vid = box.querySelector("video");
    function close() {
      box.hidden = true;
      try { vid.pause(); vid.removeAttribute("src"); vid.load(); } catch (e) {}
      document.body.style.overflow = "";
    }
    box.addEventListener("click", function (ev) {
      if (ev.target === box) close();
    });
    box.querySelector(".clip-lightbox-close").addEventListener("click", close);
    document.addEventListener("keydown", function (ev) {
      if (!box.hidden && ev.key === "Escape") close();
    });
    box._close = close;
    box._video = vid;
    return box;
  }
  function openLightbox(src, poster, title, currentTime) {
    var box = ensureLightbox();
    var vid = box._video;
    pauseAllArchiveVideos(null);
    document.getElementById("clip-lightbox-title").textContent = title || "";
    vid.poster = poster || "";
    vid.src = src;
    vid.muted = false;
    box.hidden = false;
    document.body.style.overflow = "hidden";
    function seek() {
      try {
        if (currentTime && isFinite(currentTime)) vid.currentTime = currentTime;
      } catch (e) {}
      var p = vid.play();
      if (p && p.catch) p.catch(function () {});
      vid.removeEventListener("loadedmetadata", seek);
    }
    vid.addEventListener("loadedmetadata", seek);
    vid.load();
  }
  function bindHoverPlay(root) {
    if (!root) return;
    root.querySelectorAll("video.archive-thumb, video.similar-thumb").forEach(function (v) {
      if (v.dataset.hoverBound) return;
      v.dataset.hoverBound = "1";
      var wrap = v.closest(".archive-media, .similar-media") || v;
      function start() {
        var box = document.getElementById("clip-lightbox");
        if (box && !box.hidden) return;
        pauseAllArchiveVideos(v);
        var p = v.play();
        if (p && p.catch) p.catch(function () {});
      }
      function stop() {
        var box = document.getElementById("clip-lightbox");
        if (box && !box.hidden) return;
        try { v.pause(); v.currentTime = 0; } catch (e) {}
      }
      wrap.addEventListener("mouseenter", start);
      wrap.addEventListener("mouseleave", stop);
      wrap.addEventListener("click", function (ev) {
        if (ev.target && ev.target.tagName === "A") return;
        ev.preventDefault();
        ev.stopPropagation();
        var card = v.closest(".archive-card, .similar-card");
        var titleEl = card && card.querySelector(".archive-spot, .similar-spot");
        var title = (titleEl && titleEl.textContent) || v.getAttribute("title") || "";
        openLightbox(v.currentSrc || v.src, v.getAttribute("poster") || "", title, v.currentTime || 0);
      });
    });
  }
  window.__updateSimilarArchive = renderSimilar;
  document.addEventListener("DOMContentLoaded", function () {
    bindHoverPlay(document.getElementById("archive-live"));
  });
  if (document.readyState !== "loading") {
    bindHoverPlay(document.getElementById("archive-live"));
  }
})();
"""
