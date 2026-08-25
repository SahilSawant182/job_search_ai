"""
Regression tests for:
  1. ProfileRecommendationKnowledge domain-compatibility guard
  2. RecommendationEngine TRANSITION_FIT / DIRECT_FIT / LOW_FIT classification

Run with:
  bench --site devstridenex.quantcloud.in execute job_search_ai.scratch.test_eligibility.run
"""
import frappe


def run():
    _test_domain_compat()
    _test_fit_classification()
    print("\n✓ All regression tests passed.")


# ── Test 1: Domain compatibility ──────────────────────────────────────────────

def _test_domain_compat():
    from job_search_ai.agents.career_trend.profile_recommendation_knowledge import (
        _classify_domain, _domains_compatible
    )

    cases = [
        # (branch, degree, cached_domain, expected_compatible, label)
        ("Computer Science", "B.Tech", "technology",  True,  "CSE → technology: HIT"),
        ("Information Technology", "B.Tech", "technology", True, "IT → technology: HIT"),
        ("Cybersecurity", "B.Tech", "engineering",   False, "Cybersecurity → engineering: MISS"),
        ("Computer Science", "B.Tech", "business",   False, "CSE → business: MISS"),
        ("BBA", "Operations Management", "business", True,  "BBA/Ops → business: HIT"),
        ("Psychology", "BA", "humanities",           True,  "Psychology → humanities: HIT"),
        ("Mass Communication", "BA", "humanities",   True,  "Mass Comm → humanities: HIT"),
        ("Mechanical Engineering", "B.Tech", "engineering", True, "Mech → engineering: HIT"),
        ("Mechanical Engineering", "B.Tech", "creative",   False, "Mech → creative: MISS"),
        ("Biotechnology", "B.Sc", "science",         True,  "Biotech → science: HIT"),
        ("Marketing", "BBA", "humanities",           False, "Marketing → humanities: MISS"),
        ("Human Resources", "BBA", "business",       True,  "HR → business: HIT"),
        ("Nursing", "B.Sc", "healthcare",            True,  "Nursing → healthcare: HIT"),
        ("Nursing", "B.Sc", "business",              False, "Nursing → business: MISS"),
        ("Graphic Design", "B.Des", "creative",      True,  "Design → creative: HIT"),
        ("Graphic Design", "B.Des", "technology",    False, "Design → technology: MISS"),
        ("LLB", "Law", "legal",                      True,  "Law → legal: HIT"),
        ("LLB", "Law", "business",                   False, "Law → business: MISS"),
    ]

    print("\n── Domain Compatibility Tests ──────────────────────────────────")
    failed = 0
    for branch, degree, cached_domain, expected, label in cases:
        student_domain = _classify_domain(branch, degree)
        result = _domains_compatible(student_domain, cached_domain)
        ok = result == expected
        status = "✓" if ok else "✗ FAIL"
        print(f"  {status}  {label}  (student_domain={student_domain!r})")
        if not ok:
            failed += 1
            print(f"       Expected compatible={expected}, got compatible={result}")

    assert failed == 0, f"{failed} domain compatibility test(s) failed"


# ── Test 2: FitType classification ───────────────────────────────────────────

def _test_fit_classification():
    from job_search_ai.agents.career_trend.recommendation_engine import (
        RecommendationEngine, FitType
    )
    from job_search_ai.agents.career_trend.schemas import StudentProfile

    engine = RecommendationEngine()

    class FakeCandidate:
        def __init__(self, name, degrees="", branches="", interests="",
                     req_skills=None, pref_skills=None):
            self.career_name = name
            self.suitable_degrees = degrees
            self.suitable_branches = branches
            self.applicable_branches = branches
            self.interests = interests
            self.required_skills = req_skills or []
            self.preferred_skills = pref_skills or []
            self.aliases = []
            self.skills = []
            self.career_stage = ""
            self.future_demand = ""
            self.suitable_years = ""

    # B.Tech Mechanical → Finance career (TRANSITION_FIT expected)
    stu_mech_finance = StudentProfile(
        degree="B.Tech", branch="Mechanical Engineering", year=3, country="India",
        interests=["Finance", "Investment", "Financial Modeling"],
        skills=["Excel", "Financial Modeling", "Statistics", "Python"],
    )
    finance_career = FakeCandidate(
        "Financial Analyst",
        degrees="BBA, B.Com, MBA, B.Sc Finance",
        req_skills=["Excel", "Financial Modeling", "Statistics"],
    )

    # B.Tech CSE → Software career (DIRECT_FIT expected)
    stu_cse = StudentProfile(
        degree="B.Tech", branch="Computer Science", year=3, country="India",
        interests=["Backend Development", "APIs"],
        skills=["Python", "FastAPI", "PostgreSQL"],
    )
    software_career = FakeCandidate(
        "Backend Developer",
        degrees="B.Tech, B.E, M.Tech, MCA",
        req_skills=["Python", "REST APIs", "SQL"],
    )

    # BA Arts → DevOps (LOW_FIT expected — no signal)
    stu_arts = StudentProfile(
        degree="BA", branch="Arts", year=2, country="India",
        interests=["Creative Writing"],
        skills=["MS Word"],
    )
    devops_career = FakeCandidate(
        "DevOps Engineer",
        degrees="B.Tech, B.E, MCA",
        req_skills=["Docker", "Kubernetes", "Linux", "CI/CD"],
    )

    print("\n── FitType Classification Tests ────────────────────────────────")
    tests = [
        (stu_mech_finance, finance_career,  FitType.TRANSITION_FIT, "B.Tech Mech → Finance"),
        (stu_cse,          software_career, FitType.DIRECT_FIT,     "B.Tech CSE → Backend Dev"),
        (stu_arts,         devops_career,   FitType.LOW_FIT,        "BA Arts → DevOps"),
    ]

    failed = 0
    for student, candidate, expected_fit, label in tests:
        result = engine._classify_fit(student, candidate)
        ok = result == expected_fit
        status = "✓" if ok else "✗ FAIL"
        print(f"  {status}  {label}: got {result.value!r}  (expected {expected_fit.value!r})")
        if not ok:
            failed += 1

    assert failed == 0, f"{failed} FitType test(s) failed"
