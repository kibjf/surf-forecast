# surf-forecast v1.1

Frozen 2026-09-19 (Taipei).

Includes:
- Top「今日怎麼選」with tomorrow morning 05/07/09 top-3
- Daily best cards: 早 05–09 / 中 10–14 / 晚 15:00; surf vs wind scoring (wind >6kt heavily penalized for surf)
- 今日實況 + 類似浪況 with short muted clips (hover play, click lightbox)
- No Drive links on the public page

Rollback:
```bash
git checkout v1.1 -- index.html archive/
# restore generators from this folder into /workspace (or your box paths)
cp snapshots/v1.1/*.py /workspace/
```

Git tag: `v1.1`
