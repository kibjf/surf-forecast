# Surf forecast — 第一版 (v1)

Frozen 2026-09-19 (Taipei) after:
- 今日怎麼選 + 明日早上約六點
- 每日最佳推薦（早／中／晚 × 玩浪／玩風）
- 阿浪 archive 類似浪況
- 玩浪評分：風 >6 kt 重罰

## Restore

```bash
# Pages / site files
git checkout v1 -- index.html archive/

# Generator scripts (copy back to box workspace)
cp snapshots/v1/refresh_surf_forecast.py /workspace/
cp snapshots/v1/build_similar_index.py /workspace/
cp snapshots/v1/surf_archive_ui.py /workspace/
```

Or reset whole branch (destructive): `git reset --hard v1`
