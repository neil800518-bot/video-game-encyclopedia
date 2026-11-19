"""Phase 13: read-only, labeled multi-sample ranking evaluation.

This module never changes the production image search or its weights.
The caller supplies independently labeled query samples and complete ranked
results for each strategy. A single query is not a validation dataset.
"""

from collections import Counter
from statistics import mean


def evaluate_multisample(samples, strategy_rankings, baseline="C 原始截斷"):
    """Evaluate full-index ranking lists against independent ground truth.

    samples: iterable of {'sample_id': str, 'expected_id': str, ...}
    strategy_rankings: mapping of strategy -> mapping sample_id -> ranked rows,
        where each row contains a unique 'id' and optionally 'score'.
    Returns a summary and per-sample audit. Missing results count as misses.
    """
    samples = list(samples)
    ids = [str(s["sample_id"]) for s in samples]
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate sample_id in validation dataset")
    if not samples:
        return {"summary": [], "audit": [], "sample_count": 0}
    if baseline not in strategy_rankings:
        raise ValueError("Baseline strategy missing")

    strategies = list(strategy_rankings)
    lookup = {}
    for strategy in strategies:
        lookup[strategy] = {}
        for sample in samples:
            sid = str(sample["sample_id"])
            rows = strategy_rankings[strategy].get(sid, [])
            ranks = {}
            for position, row in enumerate(rows, 1):
                game_id = str(row["id"]).strip()
                if game_id in ranks:
                    raise ValueError(f"Duplicate game ID in {strategy}/{sid}")
                ranks[game_id] = position
            lookup[strategy][sid] = ranks

    audit = []
    for sample in samples:
        sid = str(sample["sample_id"])
        expected = str(sample["expected_id"]).strip()
        base_rank = lookup[baseline][sid].get(expected)
        for strategy in strategies:
            rank = lookup[strategy][sid].get(expected)
            audit.append({
                "樣本 ID": sid,
                "正確遊戲 ID": expected,
                "策略": strategy,
                "正確遊戲排名": rank,
                "Top 1 命中": rank == 1,
                "Top 3 命中": rank is not None and rank <= 3,
                "Top 5 命中": rank is not None and rank <= 5,
                "相對基準排名提升": (
                    base_rank - rank
                    if base_rank is not None and rank is not None else None
                ),
            })

    summary = []
    for strategy in strategies:
        subset = [r for r in audit if r["策略"] == strategy]
        deltas = [r["相對基準排名提升"] for r in subset
                  if r["相對基準排名提升"] is not None]
        summary.append({
            "策略": strategy,
            "樣本數": len(subset),
            "Top 1 命中數": sum(r["Top 1 命中"] for r in subset),
            "Top 1 命中率": round(mean(r["Top 1 命中"] for r in subset) * 100, 2),
            "Top 3 命中率": round(mean(r["Top 3 命中"] for r in subset) * 100, 2),
            "Top 5 命中率": round(mean(r["Top 5 命中"] for r in subset) * 100, 2),
            "排名改善樣本數": sum(d > 0 for d in deltas),
            "排名惡化樣本數": sum(d < 0 for d in deltas),
            "無法比較排名樣本數": len(subset) - len(deltas),
        })
    return {"summary": summary, "audit": audit, "sample_count": len(samples)}
