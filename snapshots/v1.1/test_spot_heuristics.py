#!/usr/bin/env python3
"""Unit tests for local surf heuristics (no network)."""
from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from spot_heuristics import (  # noqa: E402
    MAX_ABS_DELTA,
    apply_spot_heuristics,
    find_spot,
    load_spot_heuristics,
    slot_local_dt,
    tide_events_for_spot_day,
)
from refresh_surf_forecast import (  # noqa: E402
    score_surf_slot,
    score_wind_slot,
    tip_for_pick,
)

TZ = timezone(timedelta(hours=8))
JSON_PATH = REPO / "data" / "spot-heuristics.json"


def _slot(*, hour=15, wind=5.0, wave=1.0, per=12.0, dir_deg=0.0, dir_zh="北", wave_dir_deg=90.0):
    return {
        "hour": hour,
        "wspd_kt": wind,
        "wave_m": wave,
        "wave_per_s": per,
        "dir_deg": dir_deg,
        "dir_zh": dir_zh,
        "wave_dir_deg": wave_dir_deg,
    }


def _base_surf(s, tip_west=True):
    return score_surf_slot(s, tip_west, spot_key=None)


class HeuristicsJsonTests(unittest.TestCase):
    def test_json_validates_and_has_four_spots(self):
        data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
        self.assertIsInstance(data, dict)
        self.assertIsInstance(data.get("spots"), list)
        names = {n for sp in data["spots"] for n in (sp.get("names") or [])}
        for required in (
            "竹南假日之森",
            "假日之森",
            "zhunan",
            "中角",
            "zhongjiao",
            "翡翠灣",
            "石門婚紗廣場",
            "婚紗廣場",
            "石門婚紗",
        ):
            self.assertIn(required, names)

    def test_load_from_repo_root(self):
        data = load_spot_heuristics(JSON_PATH, reload=True)
        self.assertEqual(len(data["spots"]), 4)


class MatchingTests(unittest.TestCase):
    def test_spot_key_and_aliases(self):
        cases = {
            "竹南假日之森": "zhunan-holiday-forest",
            "假日之森": "zhunan-holiday-forest",
            "zhunan": "zhunan-holiday-forest",
            "假森": "zhunan-holiday-forest",
            "中角": "zhongjiao",
            "zhongjiao": "zhongjiao",
            "翡翠灣": "feicuiwan",
            "翡灣": "feicuiwan",
            "石門婚紗廣場": "shimen-wedding-plaza",
            "婚紗廣場": "shimen-wedding-plaza",
            "石門婚紗": "shimen-wedding-plaza",
        }
        for alias, expected_id in cases.items():
            spot = find_spot(alias)
            self.assertIsNotNone(spot, alias)
            self.assertEqual(spot["id"], expected_id, alias)

    def test_unknown_spot_is_none(self):
        self.assertIsNone(find_spot("後龍"))
        self.assertIsNone(find_spot("無尾港"))
        self.assertIsNone(find_spot(""))


class AdjustmentTests(unittest.TestCase):
    def test_unknown_spot_zero_delta(self):
        delta, reasons = apply_spot_heuristics(
            "後龍", wind_kt=8, wind_dir_deg=0, wind_dir_zh="北", wave_height_m=1.2
        )
        self.assertEqual(delta, 0.0)
        self.assertEqual(reasons, [])

    def test_zhunan_penalizes_wind_and_rewards_wave_and_low_tide(self):
        dt = datetime(2026, 9, 20, 15, 0, tzinfo=TZ)
        tides = [{"type": "乾潮", "time": "14:30", "date": "2026-09-20"}]
        windy, _ = apply_spot_heuristics(
            "竹南假日之森",
            wind_kt=8.0,
            wind_dir_deg=0,
            wind_dir_zh="北",
            wave_height_m=1.0,
            slot_dt=dt,
            tide_events=tides,
        )
        calm, why = apply_spot_heuristics(
            "竹南假日之森",
            wind_kt=1.0,
            wind_dir_deg=0,
            wind_dir_zh="北",
            wave_height_m=1.0,
            slot_dt=dt,
            tide_events=tides,
        )
        self.assertLess(windy, calm)
        self.assertLess(windy, 0)  # net penalty when windy despite tide/wave bonuses
        self.assertGreater(calm, 0)
        self.assertTrue(any("乾潮" in r or "浪高" in r for r in why))

    def test_zhongjiao_offshore_west_southwest(self):
        onshore, _ = apply_spot_heuristics(
            "中角", wind_kt=8.0, wind_dir_deg=20.0, wind_dir_zh="北北東"
        )
        west, why = apply_spot_heuristics(
            "中角", wind_kt=8.0, wind_dir_deg=270.0, wind_dir_zh="西"
        )
        sw, _ = apply_spot_heuristics(
            "中角", wind_kt=8.0, wind_dir_deg=230.0, wind_dir_zh="西南"
        )
        self.assertGreater(west, onshore)
        self.assertGreater(sw, onshore)
        self.assertTrue(any("offshore" in r for r in why))
        # 225–292° window: 220° (SSW-ish) should not count; 292° should.
        just_out, _ = apply_spot_heuristics("中角", wind_kt=8.0, wind_dir_deg=220.0)
        just_in, _ = apply_spot_heuristics("中角", wind_kt=8.0, wind_dir_deg=292.0)
        self.assertLess(just_out, just_in)

    def test_feicuiwan_sensitive_above_4_5kt(self):
        light, _ = apply_spot_heuristics("翡翠灣", wind_kt=3.0, wind_dir_deg=0)
        mid, _ = apply_spot_heuristics("翡翠灣", wind_kt=5.5, wind_dir_deg=0)
        heavy, why = apply_spot_heuristics("翡翠灣", wind_kt=8.0, wind_dir_deg=0)
        self.assertEqual(light, 0.0)
        self.assertLess(mid, 0)
        self.assertLess(heavy, mid)
        self.assertIn("風敏感", why)

    def test_shimen_north_bad_ne_e_offshore_high_tide(self):
        dt = datetime(2026, 9, 20, 14, 0, tzinfo=TZ)
        tides = [{"type": "滿潮", "time": "16:00", "date": "2026-09-20"}]  # 2h before high
        north, _ = apply_spot_heuristics(
            "石門婚紗廣場",
            wind_kt=8.0,
            wind_dir_deg=5.0,
            wind_dir_zh="北",
            slot_dt=dt,
            tide_events=tides,
        )
        ne, why = apply_spot_heuristics(
            "石門婚紗廣場",
            wind_kt=8.0,
            wind_dir_deg=45.0,
            wind_dir_zh="東北",
            slot_dt=dt,
            tide_events=tides,
        )
        east, _ = apply_spot_heuristics(
            "石門婚紗廣場",
            wind_kt=8.0,
            wind_dir_deg=90.0,
            wind_dir_zh="東",
            slot_dt=dt,
            tide_events=[],
        )
        self.assertLess(north, ne)
        self.assertGreater(ne, east)  # tide bonus on NE case
        self.assertTrue(any("offshore" in r or "滿潮" in r for r in why))
        # 3h before high is in; 4h before is out; 2h after is in.
        t3, _ = apply_spot_heuristics(
            "石門婚紗",
            wind_kt=2.0,
            wind_dir_deg=180.0,
            slot_dt=datetime(2026, 9, 20, 13, 0, tzinfo=TZ),
            tide_events=tides,
        )
        t4, _ = apply_spot_heuristics(
            "石門婚紗",
            wind_kt=2.0,
            wind_dir_deg=180.0,
            slot_dt=datetime(2026, 9, 20, 11, 30, tzinfo=TZ),
            tide_events=tides,
        )
        self.assertGreater(t3, t4)

    def test_delta_does_not_dominate(self):
        dt = datetime(2026, 9, 20, 15, 0, tzinfo=TZ)
        tides = [
            {"type": "乾潮", "time": "15:00", "date": "2026-09-20"},
            {"type": "滿潮", "time": "15:00", "date": "2026-09-20"},
        ]
        for key in ("竹南假日之森", "中角", "翡翠灣", "石門婚紗廣場"):
            delta, _ = apply_spot_heuristics(
                key,
                wind_kt=12.0,
                wind_dir_deg=270.0,
                wind_dir_zh="西",
                wave_height_m=1.5,
                slot_dt=dt,
                tide_events=tides,
            )
            self.assertLessEqual(abs(delta), MAX_ABS_DELTA)


class ScorerIntegrationTests(unittest.TestCase):
    def test_spots_without_heuristics_unchanged(self):
        s = _slot(wind=7.0, wave=1.1, per=14.0, dir_deg=20, wave_dir_deg=80)
        base = _base_surf(s, tip_west=True)
        for key in ("後龍", "松柏港", "無尾港", "烏石"):
            self.assertAlmostEqual(
                score_surf_slot(s, True, spot_key=key),
                base,
                places=6,
                msg=key,
            )

    def test_wind_sport_scorer_untouched(self):
        s = _slot(wind=18.0, wave=0.8)
        a = score_wind_slot(s, tip_west=True)
        b = score_wind_slot(s, tip_west=True)
        self.assertEqual(a, b)
        # Heuristic kwargs must not exist on wind scorer; surf-only path.
        self.assertEqual(score_wind_slot.__code__.co_argcount, 2)

    def test_surf_score_moves_for_heuristic_spots(self):
        s = _slot(hour=15, wind=8.0, wave=1.0, per=12.0, dir_deg=270, dir_zh="西")
        base = _base_surf(s, tip_west=True)
        zhunan = score_surf_slot(s, True, spot_key="竹南假日之森")
        self.assertLess(zhunan, base)  # wind not calm
        zhong = score_surf_slot(s, False, spot_key="中角")
        base_east = _base_surf(s, tip_west=False)
        self.assertGreater(zhong, base_east)  # W offshore
        fei = score_surf_slot(s, False, spot_key="翡翠灣")
        self.assertLess(fei, base_east)

    def test_tip_appends_one_clause(self):
        sp = {"tip_west": False, "key": "中角"}
        s = _slot(wind=5.0, wave=1.0)
        text = tip_for_pick("surf", sp, s, ["西／西南偏 offshore"])
        self.assertTrue(text.endswith("（西／西南偏 offshore）"))
        again = tip_for_pick("surf", sp, s, ["西／西南偏 offshore"])
        self.assertEqual(again.count("offshore"), 1)
        wind_tip = tip_for_pick("wind", sp, s, ["西／西南偏 offshore"])
        self.assertNotIn("offshore", wind_tip)

    def test_tide_events_helper_reads_pipeline_shape(self):
        tides = {
            "竹南假日之森": {
                "days": {
                    "2026-09-20": [
                        {"type": "乾潮", "time": "08:10", "height_cm": -40},
                        {"type": "滿潮", "time": "15:20", "height_cm": 80},
                    ]
                }
            }
        }
        ev = tide_events_for_spot_day(tides, "竹南假日之森", "2026-09-20")
        self.assertEqual(len(ev), 2)
        dt = slot_local_dt("2026-09-20", 7)
        self.assertEqual(dt.hour, 7)
        delta, why = apply_spot_heuristics(
            "竹南假日之森",
            wind_kt=1.0,
            wave_height_m=0.9,
            slot_dt=dt,
            tide_events=ev,
        )
        self.assertGreater(delta, 0)
        self.assertTrue(any("乾潮" in r for r in why))


class PipelineWiringTests(unittest.TestCase):
    def _forecast(self):
        from refresh_surf_forecast import DAYS, SPOTS, TODAY

        def slots():
            out = []
            for h in (5, 7, 9, 12, 15):
                out.append(
                    _slot(
                        hour=h,
                        wind=7.0,
                        wave=1.0,
                        per=14.0,
                        dir_deg=45.0,
                        dir_zh="東北",
                        wave_dir_deg=90.0,
                    )
                )
            return out

        spots = {}
        tides = {}
        for sp in SPOTS:
            spots[sp["key"]] = {"days": {TODAY: slots(), DAYS[1]: slots()}}
            tides[sp["key"]] = {
                "days": {
                    TODAY: [
                        {"type": "乾潮", "time": "15:00", "height_cm": -20},
                        {"type": "滿潮", "time": "08:00", "height_cm": 70},
                    ],
                    DAYS[1]: [
                        {"type": "乾潮", "time": "07:00", "height_cm": -20},
                        {"type": "滿潮", "time": "14:00", "height_cm": 70},
                    ],
                }
            }
        return {"spots": spots, "tides": tides}, tides

    def test_today_tomorrow_daily_best_use_heuristics(self):
        from refresh_surf_forecast import (
            TODAY,
            compute_daily_best,
            pick_today_recommendation,
            pick_tomorrow_morning_recommendation,
        )

        forecast, tides = self._forecast()
        pick, rec = pick_today_recommendation(forecast, tides)
        self.assertTrue(pick)
        self.assertTrue(rec.startswith("今日首選") or "衝浪優先" in rec)
        pick_tm, html = pick_tomorrow_morning_recommendation(forecast, tides=tides)
        self.assertTrue(pick_tm)
        self.assertIn("明日早上推薦", html)
        daily = compute_daily_best(forecast, TODAY, tides=tides)
        surf_best = daily["by"][TODAY]["晚"]["surf"]["best"]
        wind_best = daily["by"][TODAY]["晚"]["wind"]["best"]
        self.assertIsNotNone(surf_best)
        self.assertIsNotNone(wind_best)
        # Wind-sport payload score is still the wind scorer (no heuristic).
        wind_slot = _slot(hour=15, wind=7.0, wave=1.0, per=14.0, dir_deg=45, dir_zh="東北", wave_dir_deg=90)
        self.assertAlmostEqual(wind_best["score"], round(score_wind_slot(wind_slot, wind_best["tip_west"]), 2))
        # Heuristic spots mention a local-experience clause at most once on surf tips.
        if surf_best["key"] in ("竹南假日之森", "中角", "翡翠灣", "石門婚紗廣場"):
            self.assertLessEqual(surf_best["tip"].count("（"), 1)


if __name__ == "__main__":
    unittest.main()
