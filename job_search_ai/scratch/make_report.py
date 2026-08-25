#!/usr/bin/env python3
"""Generate benchmark report from intermediate JSON files (no Frappe needed)."""
import json, sys
from pathlib import Path

OUT = Path("/home/dev/frappe-bench/apps/job_search_ai/job_search_ai/scratch")

def load(n): 
    f = OUT / f"benchmark_intermediate_{n}.json"
    return json.loads(f.read_text()) if f.exists() else []

def pct(lst, fn): return sum(1 for r in lst if fn(r)) / len(lst) * 100 if lst else 0
def avg(lst): return sum(lst)/len(lst) if lst else 0

def report(label, records):
    total = len(records)
    correct   = [r for r in records if r["correct"]]
    has_recs  = [r for r in records if r["recs"]]
    empties   = [r for r in records if not r["recs"]]
    pkb_hits  = [r for r in records if r["pkb_hit"]]
    kb_hits   = [r for r in records if r["knowledge_hit"]]
    tav_used  = [r for r in records if r["tavily_used"]]
    llm_used  = [r for r in records if r["llm_used"]]

    hit_rec   = [r for r in records if r["pkb_hit"]]
    miss_rec  = [r for r in records if not r["pkb_hit"]]

    # Domain accuracy breakdown
    domain_groups = {}
    for r in records:
        dom = r.get("name","").split()[-1] if r.get("name") else "Unknown"
        domain_groups.setdefault(dom, []).append(r)

    # Time breakdown (only MISS records have meaningful stage timings)
    miss_with_time = [r for r in miss_rec if r["t_total"] > 0.5]
    avg_tav  = avg([r["t_tavily"]       for r in miss_with_time]) if miss_with_time else 0
    avg_kb   = avg([r["t_kb_build"]     for r in miss_with_time]) if miss_with_time else 0
    avg_llm  = avg([r["t_llm_synthesis"] for r in miss_with_time]) if miss_with_time else 0
    avg_ret  = avg([r["t_retrieval_est"] for r in miss_with_time]) if miss_with_time else 0
    avg_tot  = avg([r["t_total"]         for r in miss_with_time]) if miss_with_time else 0
    avg_tot_hit = avg([r["t_total"] for r in hit_rec]) if hit_rec else 0
    avg_tot_all = avg([r["t_total"] for r in records])

    failure_causes: dict = {}
    for r in records:
        if not r["correct"]:
            fs = r["failure_stage"] if r["failure_stage"] != "none" else (
                "wrong_career_in_family_match" if r["recs"] else "empty_recs"
            )
            failure_causes[fs] = failure_causes.get(fs, 0) + 1

    lines = []
    W = 66

    def box(text): lines.append(f"║  {text:<{W-4}}║")
    def sep(): lines.append(f"╠{'═'*W}╣")
    def top(): lines.append(f"╔{'═'*W}╗")
    def bot(): lines.append(f"╚{'═'*W}╝")

    top()
    box(f"BENCHMARK REPORT — {label}")
    sep()
    box(f"ACCURACY  (career-family matching, not strict goal)")
    box(f"  Has recommendations : {len(has_recs):>3} / {total}  ({pct(records, lambda r: r['recs']):.1f}%)")
    box(f"  Career-family match : {len(correct):>3} / {total}  ({pct(records, lambda r: r['correct']):.1f}%)")
    box(f"  Empty responses     : {len(empties):>3} / {total}  ({pct(records, lambda r: not r['recs']):.1f}%)")
    sep()
    box(f"CACHE PERFORMANCE")
    box(f"  Profile KB HITs     : {len(pkb_hits):>3} / {total}  ({pct(records, lambda r: r['pkb_hit']):.1f}%)")
    box(f"  Career KB HITs      : {len(kb_hits):>3} / {total}  ({pct(records, lambda r: r['knowledge_hit']):.1f}%)")
    box(f"  Tavily calls used   : {len(tav_used):>3} / {total}  ({pct(records, lambda r: r['tavily_used']):.1f}%)")
    box(f"  LLM synthesis used  : {len(llm_used):>3} / {total}  ({pct(records, lambda r: r['llm_used']):.1f}%)")
    sep()
    box(f"LATENCY")
    box(f"  Avg HIT latency     : {avg_tot_hit*1000:>7.0f} ms")
    box(f"  Avg MISS latency    : {avg_tot*1000:>7.0f} ms  (Tavily/LLM path)")
    box(f"  Avg overall latency : {avg_tot_all*1000:>7.0f} ms")
    sep()
    box(f"TIME BREAKDOWN (MISS path, avg seconds)")
    box(f"  MariaDB retrieval   : {avg_ret:>7.3f}s  ({avg_ret/max(avg_tot,0.001)*100:.1f}%)")
    box(f"  Tavily search       : {avg_tav:>7.3f}s  ({avg_tav/max(avg_tot,0.001)*100:.1f}%)")
    box(f"  KnowledgeBuilder    : {avg_kb:>7.3f}s  ({avg_kb/max(avg_tot,0.001)*100:.1f}%)")
    box(f"  LLM synthesis       : {avg_llm:>7.3f}s  ({avg_llm/max(avg_tot,0.001)*100:.1f}%)")
    sep()
    box(f"TOP FAILURE CAUSES  (incorrect + empty combined)")
    if failure_causes:
        for cause, cnt in sorted(failure_causes.items(), key=lambda x:-x[1])[:6]:
            box(f"  {cause:<40} : {cnt}")
    else:
        box(f"  None")
    bot()

    # Per-profile table
    lines.append("")
    lines.append(f"{'ID':<8} {'Name':<30} {'Top Career':<34} {'OK':^4} {'PKB':^5} {'KHit':^5} {'Tav':^4} {'ms':>7}  Fail-Stage")
    lines.append("-"*120)
    for r in records:
        top_c = (r["recs"][0] if r["recs"] else "(empty)")[:33]
        ok  = "✓" if r["correct"] else ("∅" if not r["recs"] else "✗")
        pkb = "HIT" if r["pkb_hit"] else "---"
        kh  = "HIT" if r["knowledge_hit"] else "---"
        tv  = "Y" if r["tavily_used"] else "N"
        ms  = int(r["t_total"] * 1000)
        fs  = r["failure_stage"] if not r["correct"] else ""
        nm  = r.get("name","")[:29]
        lines.append(f"{r['profile_id']:<8} {nm:<30} {top_c:<34} {ok:^4} {pkb:^5} {kh:^5} {tv:^4} {ms:>7}  {fs}")

    # Incorrect deep-dive
    bad = [r for r in records if not r["correct"]]
    if bad:
        lines.append(f"\n{'─'*80}")
        lines.append(f"INCORRECT / EMPTY RECOMMENDATIONS — ROOT CAUSE ANALYSIS")
        lines.append(f"{'─'*80}")
        for r in bad:
            lines.append(f"\n  {r['profile_id']}: {r.get('name','')}")
            lines.append(f"    Goal           : {r.get('goal','')}")
            lines.append(f"    Actual recs    : {r['recs']}")
            lines.append(f"    Acceptable     : {r['acceptable_family'][:3]}")
            lines.append(f"    Failure stage  : {r['failure_stage']}")
            lines.append(f"    PKB            : hit={r['pkb_hit']} sim={r['pkb_similarity']:.3f}")
            lines.append(f"    Career KB      : hit={r['knowledge_hit']} count={r['knowledge_count']}")
            lines.append(f"    Tavily used    : {r['tavily_used']}")
            lines.append(f"    Error          : {r.get('error') or 'none'}")

    return "\n".join(lines)


def comparison(r1, r2):
    # Align on common profiles
    ids2 = {r["profile_id"]: r for r in r2}
    common = [r for r in r1 if r["profile_id"] in ids2]
    r2c = [ids2[r["profile_id"]] for r in common]
    n = len(common)

    rows = [
        ("Profiles evaluated",         n,                                    n),
        ("Has recommendations (%)",    pct(r1,  lambda r: bool(r["recs"])), pct(r2c, lambda r: bool(r["recs"]))),
        ("Career-correct (%)",         pct(r1,  lambda r: r["correct"]),    pct(r2c, lambda r: r["correct"])),
        ("Empty responses (%)",        pct(r1,  lambda r: not r["recs"]),   pct(r2c, lambda r: not r["recs"])),
        ("Avg total latency (ms)",     avg([r["t_total"]*1000 for r in r1]),avg([r["t_total"]*1000 for r in r2c])),
        ("Avg MISS latency (ms)",      avg([r["t_total"]*1000 for r in r1 if not r["pkb_hit"]]),
                                       avg([r["t_total"]*1000 for r in r2c if not r["pkb_hit"]])),
        ("Total Tavily calls",         sum(r.get("tavily_calls",0) for r in r1), sum(r.get("tavily_calls",0) for r in r2c)),
        ("Profiles used LLM",          sum(1 for r in r1 if r["llm_used"]), sum(1 for r in r2c if r["llm_used"])),
    ]

    lines = []
    lines.append(f"\n{'─'*70}")
    lines.append(f"COMPARISON: _MAX_MISS_INTERESTS = 1  vs  2  (n={n} common profiles)")
    lines.append(f"{'─'*70}")
    lines.append(f"{'Metric':<35} {'=1':>10}  {'=2':>10}  {'Delta':>10}")
    lines.append(f"{'─'*70}")
    for name, v1, v2 in rows:
        delta = v2 - v1
        sign  = "+" if delta >= 0 else ""
        lines.append(f"{name:<35} {v1:>10.2f}  {v2:>10.2f}  {sign}{delta:>9.2f}")
    lines.append(f"{'─'*70}")
    lines.append(f"\nVERDICT:")
    acc_delta = pct(r2c, lambda r: r["correct"]) - pct(r1, lambda r: r["correct"])
    lat_delta = avg([r["t_total"]*1000 for r in r2c]) - avg([r["t_total"]*1000 for r in r1])
    lines.append(f"  Accuracy gain from 1→2 interests : {acc_delta:+.1f}%")
    lines.append(f"  Latency cost from 1→2 interests  : {lat_delta:+.0f} ms avg")
    if acc_delta >= 3 and lat_delta < 10000:
        lines.append(f"  → KEEP _MAX_MISS_INTERESTS=2  (meaningful accuracy gain, acceptable cost)")
    elif acc_delta < 1:
        lines.append(f"  → REVERT to _MAX_MISS_INTERESTS=1  (no meaningful accuracy gain)")
    else:
        lines.append(f"  → Marginal — consider keeping =2 only for non-tech streams")
    return "\n".join(lines)


if __name__ == "__main__":
    r1 = load(1)
    r2 = load(2)

    if not r1:
        print("ERROR: benchmark_intermediate_1.json not found"); sys.exit(1)

    output_parts = [
        "CAREER RECOMMENDATION — DIAGNOSTIC BENCHMARK",
        "=" * 68,
        report("MAX_MISS_INTERESTS=1  (60 profiles)", r1),
    ]
    if r2:
        output_parts.append(report(f"MAX_MISS_INTERESTS=2  ({len(r2)} profiles)", r2))
        output_parts.append(comparison(r1, r2))

    text = "\n".join(output_parts)
    print(text)
    out_file = OUT / "benchmark_report.txt"
    out_file.write_text(text)
    print(f"\n✓ Report written to {out_file}")
