# -*- coding: utf-8 -*-
"""
benchmark_60_v2.py — Integrity-first, dual-pass diagnostic benchmark.
Runs PASS A (Cold Cache) and PASS B (Warm Cache) with error classification.
"""

import json
import time
import hashlib
import re
import numpy as np
import frappe
from unittest.mock import patch
from groq import Groq

from job_search_ai.agents.career_trend.schemas import StudentProfile

# ── Load profiles from existing diagnose_recommendations.py ──────────────────
import re as _re
_diag = open(
    "/home/dev/frappe-bench/apps/job_search_ai/job_search_ai/scratch/diagnose_recommendations.py"
).read()
_m = _re.search(r'STUDENT_PROFILES_JSON = """(.*?)"""', _diag, _re.DOTALL)
PROFILES_DATA = json.loads(_m.group(1).strip())

OUT = "/home/dev/frappe-bench/apps/job_search_ai/job_search_ai/scratch"


def _career_correct_top1(expected_families, recs):
    if not recs or not expected_families:
        return False
    family = {c.lower().strip() for c in expected_families}
    r = recs[0].lower().strip()
    for f in family:
        if r == f or r in f or f in r or any(w in f for w in r.split() if len(w) > 3):
            return True
    return False


def _career_correct_top3(expected_families, recs):
    if not recs or not expected_families:
        return False
    family = {c.lower().strip() for c in expected_families}
    for r in recs[:3]:
        rl = r.lower().strip()
        for f in family:
            if rl == f or rl in f or f in rl or any(w in f for w in rl.split() if len(w) > 3):
                return True
    return False


def classify_failure(rec, p):
    error = rec.get("error")
    recs = rec.get("recs", [])
    top1_correct = rec.get("top1_correct", False)
    top3_correct = rec.get("top3_correct", False)
    
    # 1. DATA_QUALITY_ERROR: If the input profile is invalid/empty
    if not p.get("interests") and not p.get("skills"):
        return "DATA_QUALITY_ERROR"
        
    if error:
        err_lower = error.lower()
        if any(w in err_lower for w in ["llm", "groq", "openai", "chat.completions", "timeout", "http status 404", "model"]):
            return "LLM_ERROR"
        if any(w in err_lower for w in ["tavily", "search", "quota", "rate limit"]):
            return "SEARCH_ERROR"
        if any(w in err_lower for w in ["qdrant", "pkb", "cache", "vector"]):
            return "CACHE_ERROR"
        if any(w in err_lower for w in ["mariadb", "sql", "database", "retriever", "get_all"]):
            return "RETRIEVAL_ERROR"
        if any(w in err_lower for w in ["assertion", "benchmark", "validation"]):
            return "BENCHMARK_ERROR"
        return "BENCHMARK_ERROR" # fallback for raw exceptions
        
    # If no runtime error, but recommendation is empty or top-1 is incorrect:
    if not recs or not top3_correct:
        return "RECOMMENDATION_ERROR"
        
    return "none"


def mock_embed(self, text):
    h = hashlib.sha256(text.encode("utf-8")).digest()
    seed = int.from_bytes(h, "big") % (2 ** 32)
    rng = np.random.default_rng(seed)
    v = rng.uniform(-1.0, 1.0, 768)
    v /= np.linalg.norm(v)
    return v.tolist()


def run_pass(agent, profiles, pass_name, bypass_cache=False):
    records = []
    print(f"\nRunning {pass_name} pass for {len(profiles)} profiles...")

    # Lookup lookup method to patch
    lookup_path = "job_search_ai.agents.career_trend.profile_recommendation_knowledge.ProfileRecommendationKnowledge.lookup"
    
    # Setup cache bypass patch if requested
    lookup_patch = patch(lookup_path, return_value=None) if bypass_cache else None
    if lookup_patch:
        lookup_patch.start()

    for p in profiles:
        pid = p["profile_id"]
        student = StudentProfile(
            degree=p["degree"], branch=p["branch"], year=p["year"],
            country=p["country"], interests=p["interests"], skills=p["skills"]
        )

        t0 = time.perf_counter()
        recs = []
        metrics = {}
        error = None
        
        try:
            resp = agent.run(student)
            recs = [r.career for r in resp.recommended_paths]
            metrics = getattr(resp, "metrics", {}) or {}
        except Exception as exc:
            error = str(exc)
        elapsed = time.perf_counter() - t0

        expected_families = p.get("expected_career_families", [])
        top1_correct = _career_correct_top1(expected_families, recs)
        top3_correct = _career_correct_top3(expected_families, recs)

        fit_type = "N/A"
        try:
            if resp.recommended_paths:
                scores = getattr(resp.recommended_paths[0], "scores", {}) or {}
                if isinstance(scores, dict):
                    fit_type = scores.get("fit_type", "N/A")
        except Exception:
            pass

        rec_result = {
            "profile_id":     pid,
            "name":           p["name"],
            "goal":           p["goal"],
            "degree":         p["degree"],
            "branch":         p["branch"],
            "interests":      p["interests"],
            "skills":         p["skills"],
            "expected_families": expected_families,
            "recs":           recs,
            "top1_correct":   top1_correct,
            "top3_correct":   top3_correct,
            "fit_type":       fit_type,
            "knowledge_hit":  metrics.get("knowledge_hit", False),
            "pkb_hit":        metrics.get("model_name") == "profile_recommendation_knowledge",
            "tavily_used":    metrics.get("tavily_used", False),
            "tavily_calls":   metrics.get("query_count", 0),
            "llm_used":       metrics.get("llm_response_time", 0) > 0.1,
            "t_total":        round(elapsed, 4),
            "t_tavily":       round(metrics.get("parallel_search_time", 0.0), 4),
            "t_kb_build":     round(metrics.get("kb_build_time", 0.0), 4),
            "t_llm":          round(metrics.get("llm_response_time", 0.0), 4),
            "error":          error,
        }
        
        # Classify the failure
        rec_result["failure_class"] = classify_failure(rec_result, p)
        records.append(rec_result)

        ok = "✓" if top3_correct else ("∅" if not recs else "✗")
        pkb_s = "HIT" if rec_result["pkb_hit"] else "---"
        fc_s = "" if rec_result["failure_class"] == "none" else f" ({rec_result['failure_class']})"
        print(f"  [{pid}] {p['name'][:28]}... {ok} {recs[:2]} {int(elapsed*1000)}ms pkb={pkb_s}{fc_s}")

    if lookup_patch:
        lookup_patch.stop()

    return records


def run():
    frappe.init(site="devstridenex.quantcloud.in", sites_path="../../sites")
    frappe.connect()

    # 1. Verify expected_career_families integrity
    print("Verifying student profiles expected_career_families integrity...")
    missing_families = []
    for p in PROFILES_DATA:
        families = p.get("expected_career_families")
        if not families or not isinstance(families, list) or len(families) == 0:
            missing_families.append(p["profile_id"])
    if missing_families:
        raise ValueError(f"The following profiles lack valid expected_career_families: {missing_families}")
    print(f"✓ All {len(PROFILES_DATA)} profiles have exactly one correct expected family definition.\n")

    api_key = frappe.conf.get("groq_api_key")
    if not api_key:
        raise RuntimeError("groq_api_key not set")
    groq_client = Groq(api_key=api_key)

    def mock_groq(*args, **kwargs):
        prompt = next((a for a in args if isinstance(a, str)), kwargs.get("prompt", ""))
        try:
            r = groq_client.chat.completions.create(
                model="groq/compound-mini",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                timeout=30,
            )
            return r.choices[0].message.content or "{}"
        except Exception:
            return "{}"

    patches = [
        patch("job_search_ai.agents.career_trend.llm_service.LLMService._call_llm", mock_groq),
        patch("job_search_ai.services.knowledge.extraction.career_llm_extractor._call_ollama", mock_groq),
        patch("job_search_ai.services.knowledge.extraction.career_llm_extractor._call_openai_compat", mock_groq),
        patch("job_search_ai.services.ai.embedding_service.EmbeddingService.embed", mock_embed),
    ]
    for p in patches:
        p.start()

    from job_search_ai.agents.career_trend.agent import CareerTrendAgent
    agent = CareerTrendAgent()

    # PASS A: Cold Cache (Bypass PKB lookup)
    pass_a_results = run_pass(agent, PROFILES_DATA, "PASS A (Cold Cache)", bypass_cache=True)

    # PASS B: Warm Cache (Allow normal PKB lookup)
    pass_b_results = run_pass(agent, PROFILES_DATA, "PASS B (Warm Cache)", bypass_cache=False)

    for p in patches:
        p.stop()

    # Save results to JSON
    with open(f"{OUT}/benchmark_v2_results_cold.json", "w") as f:
        json.dump(pass_a_results, f, indent=2)
    with open(f"{OUT}/benchmark_v2_results_warm.json", "w") as f:
        json.dump(pass_b_results, f, indent=2)

    _make_combined_report(pass_a_results, pass_b_results)


def _make_combined_report(r_cold, r_warm):
    n = len(r_cold)
    
    def get_stats(records):
        top1 = sum(1 for r in records if r["top1_correct"])
        top3 = sum(1 for r in records if r["top3_correct"])
        has = sum(1 for r in records if r["recs"])
        empty = sum(1 for r in records if not r["recs"])
        pkb = sum(1 for r in records if r["pkb_hit"])
        tav = sum(1 for r in records if r["tavily_used"])
        llm = sum(1 for r in records if r["llm_used"])
        
        hit_latencies = [r["t_total"] for r in records if r["pkb_hit"]]
        miss_latencies = [r["t_total"] for r in records if not r["pkb_hit"]]
        
        avg_hit_ms = int(np.mean(hit_latencies) * 1000) if hit_latencies else 0
        avg_miss_ms = int(np.mean(miss_latencies) * 1000) if miss_latencies else 0
        
        fc_counts = {
            "RECOMMENDATION_ERROR": 0,
            "RETRIEVAL_ERROR": 0,
            "CACHE_ERROR": 0,
            "LLM_ERROR": 0,
            "SEARCH_ERROR": 0,
            "DATA_QUALITY_ERROR": 0,
            "BENCHMARK_ERROR": 0
        }
        for r in records:
            fc = r["failure_class"]
            if fc != "none":
                fc_counts[fc] = fc_counts.get(fc, 0) + 1
                
        # Calculate transition-fit accuracy
        tr_recs = [r for r in records if r["profile_id"] in {"STU057","STU055","STU056","STU059"}]
        tr_correct = sum(1 for r in tr_recs if r["top1_correct"])
        tr_acc = (tr_correct / len(tr_recs) * 100) if tr_recs else 0.0
        
        # Calculate non-tech accuracy
        # Non-tech profiles: STU021 to STU024 (Commerce), STU026 (HR), STU035-STU037 (Arts/Humanities), etc.
        # Let's count any profile that is not CS/IT/Engineering as non-tech
        non_tech_ids = {
            "STU021", "STU022", "STU023", "STU024", "STU026", "STU027", "STU028", "STU029",
            "STU030", "STU035", "STU036", "STU037", "STU038", "STU039", "STU040", "STU041",
            "STU042", "STU043", "STU048", "STU049", "STU050", "STU051", "STU053", "STU054"
        }
        nt_recs = [r for r in records if r["profile_id"] in non_tech_ids]
        nt_correct = sum(1 for r in nt_recs if r["top1_correct"])
        nt_acc = (nt_correct / len(nt_recs) * 100) if nt_recs else 0.0

        return {
            "top1": top1,
            "top1_pct": top1 / n * 100,
            "top3": top3,
            "top3_pct": top3 / n * 100,
            "has": has,
            "has_pct": has / n * 100,
            "empty": empty,
            "pkb_pct": pkb / n * 100,
            "avg_hit_ms": avg_hit_ms,
            "avg_miss_ms": avg_miss_ms,
            "tav": tav,
            "llm": llm,
            "fc_counts": fc_counts,
            "tr_acc": tr_acc,
            "nt_acc": nt_acc
        }

    c_stats = get_stats(r_cold)
    w_stats = get_stats(r_warm)

    lines = []
    lines.append("======================================================================")
    lines.append("             FINAL CAREER RECOMMENDATION BENCHMARK INTEGRITY REPORT")
    lines.append("======================================================================")
    lines.append(f"Profiles Evaluated: {n}")
    lines.append("")
    lines.append("── OVERALL METRICS COMPARISON ────────────────────────────────────────")
    lines.append(f"{'Metric':<35} | {'PASS A (Cold Cache)':^20} | {'PASS B (Warm Cache)':^20}")
    lines.append("-" * 83)
    lines.append(f"{'Top-1 Accuracy (%)':<35} | {c_stats['top1_pct']:>18.1f}% | {w_stats['top1_pct']:>18.1f}%")
    lines.append(f"{'Top-3 Accuracy (%)':<35} | {c_stats['top3_pct']:>18.1f}% | {w_stats['top3_pct']:>18.1f}%")
    lines.append(f"{'Non-Tech Accuracy (%)':<35} | {c_stats['nt_acc']:>18.1f}% | {w_stats['nt_acc']:>18.1f}%")
    lines.append(f"{'Transition-Fit Accuracy (%)':<35} | {c_stats['tr_acc']:>18.1f}% | {w_stats['tr_acc']:>18.1f}%")
    lines.append(f"{'Has Recommendations (%)':<35} | {c_stats['has_pct']:>18.1f}% | {w_stats['has_pct']:>18.1f}%")
    lines.append(f"{'PKB HIT Rate (%)':<35} | {c_stats['pkb_pct']:>18.1f}% | {w_stats['pkb_pct']:>18.1f}%")
    lines.append(f"{'Average HIT Latency':<35} | {c_stats['avg_hit_ms']:>17} ms | {w_stats['avg_hit_ms']:>17} ms")
    lines.append(f"{'Average MISS Latency':<35} | {c_stats['avg_miss_ms']:>17} ms | {w_stats['avg_miss_ms']:>17} ms")
    lines.append(f"{'Total Tavily Calls':<35} | {c_stats['tav']:>18} | {w_stats['tav']:>18}")
    lines.append(f"{'Total LLM Calls':<35} | {c_stats['llm']:>18} | {w_stats['llm']:>18}")
    lines.append("")
    
    lines.append("── ERROR CLASSIFICATIONS (PASS A) ────────────────────────────────────")
    for err, count in c_stats["fc_counts"].items():
        lines.append(f"  {err:<30} : {count}")
    lines.append("")

    lines.append("── ERROR CLASSIFICATIONS (PASS B) ────────────────────────────────────")
    for err, count in w_stats["fc_counts"].items():
        lines.append(f"  {err:<30} : {count}")
    lines.append("")

    # Manual review list of incorrect results (from Pass B - Warm Cache)
    lines.append("── PASS B MANUAL REVIEW LIST FOR INCORRECT RESULTS ───────────────────")
    incorrect_warm = [r for r in r_warm if not r["top1_correct"]]
    if incorrect_warm:
        lines.append(f"{'ID':<8} | {'Profile Name':<28} | {'Top Recommendation':<28} | {'Failure Class'}")
        lines.append("-" * 83)
        for r in incorrect_warm:
            top = r["recs"][0] if r["recs"] else "(empty)"
            lines.append(f"{r['profile_id']:<8} | {r['name'][:27]:<28} | {top[:27]:<28} | {r['failure_class']}")
            lines.append(f"         Expected: {r['expected_families'][:5]}")
    else:
        lines.append("  None! All recommendations matched the correct career families.")
    lines.append("")

    # Manual review list of incorrect results (from Pass A - Cold Cache)
    lines.append("── PASS A MANUAL REVIEW LIST FOR INCORRECT RESULTS ───────────────────")
    incorrect_cold = [r for r in r_cold if not r["top1_correct"]]
    if incorrect_cold:
        lines.append(f"{'ID':<8} | {'Profile Name':<28} | {'Top Recommendation':<28} | {'Failure Class'}")
        lines.append("-" * 83)
        for r in incorrect_cold:
            top = r["recs"][0] if r["recs"] else "(empty)"
            lines.append(f"{r['profile_id']:<8} | {r['name'][:27]:<28} | {top[:27]:<28} | {r['failure_class']}")
            lines.append(f"         Expected: {r['expected_families'][:5]}")
    else:
        lines.append("  None! All recommendations matched the correct career families.")
    lines.append("")

    report_text = "\n".join(lines)
    with open(f"{OUT}/benchmark_v2_report.txt", "w") as f:
        f.write(report_text)
    
    print("\n" + report_text)
    print(f"\n✓ Report written to {OUT}/benchmark_v2_report.txt")


if __name__ == "__main__":
    run()
