import frappe
from job_search_ai.agents.skill_agent.skill_agent import SkillAgent
from job_search_ai.agents.skill_agent.schemas import SkillRequest
from job_search_ai.services.skill_gap.normalizer import normalize_skill, get_skill_key
from job_search_ai.agents.skill_agent.validator import calculate_relevance_metrics, get_career_group_indices
import time
import os

VAGUE_SKILLS = {
    "systems",
    "apidevelopment",
    "apidevelopmentbasics",
    "databasemanagement",
    "cloudcomputingconcepts"
}

def clear_cache():
    import requests
    from job_search_ai.services.settings_service import SettingsService
    from job_search_ai.agents.skill_agent.knowledge_cache import SkillKnowledgeCache
    settings = SettingsService.get()
    cache = SkillKnowledgeCache(settings)
    url = f"{cache.qdrant_url}/collections/{cache.collection}"
    print(f"Clearing cache collection: {url}")
    try:
        resp = requests.delete(url, timeout=10)
        print(f"Cache clear response: {resp.status_code}")
    except Exception as e:
        print(f"Cache clear failed: {e}")

def run_audit():
    clear_cache()
    roles = [
        "Frontend Developer",
        "Backend Developer",
        "Full Stack Developer",
        "DevOps Engineer",
        "AI Engineer",
        "Data Scientist",
        "Frappe Developer"
    ]
    
    agent = SkillAgent()
    output_lines = []
    
    def log(msg):
        print(msg)
        output_lines.append(msg)
        
    log("=================== STARTING CAREER-AUTHORITY AUDIT ===================")
    
    from job_search_ai.agents.skill_agent.doctype_writer import _resolve_job_profile
    
    for role in roles:
        log(f"\n--- CAREER: {role} ---")
        
        # 1. Load authoritative skills
        ck_name = _resolve_job_profile(role)
        auth_skills_raw = []
        if ck_name:
            auth_skills_raw = frappe.db.sql(
                "SELECT skill_name FROM `tabCareer Knowledge Skill` WHERE parent = %s",
                (ck_name,),
                as_dict=True
            )
            auth_skills_raw = [s["skill_name"] for s in auth_skills_raw if s.get("skill_name")]
        
        # 2. Canonicalize authoritative skills
        auth_canonical = []
        auth_keys = set()
        for s in auth_skills_raw:
            canonical = normalize_skill(s)
            key = get_skill_key(s)
            if key and key not in auth_keys:
                auth_keys.add(key)
                auth_canonical.append(canonical)
                
        # 3. Generate profile
        t0 = time.perf_counter()
        res = agent.run(SkillRequest(role=role), save_to_doctype=False)
        t_duration = time.perf_counter() - t0
        
        profile = res.profile
        metrics = res.metrics
        
        # 4. Collect and canonicalize generated skills
        gen_by_tier = {
            "Foundation": profile.foundation_skills,
            "Core Domain": profile.core_domain_skills,
            "Industry": profile.industry_skills,
            "Emerging": profile.emerging_skills
        }
        
        all_gen_skills = (
            profile.foundation_skills +
            profile.core_domain_skills +
            profile.industry_skills +
            profile.emerging_skills
        )
        
        gen_canonical = []
        gen_keys = set()
        duplicates_found = []
        for s in all_gen_skills:
            canonical = normalize_skill(s)
            key = get_skill_key(s)
            if key:
                if key in gen_keys:
                    duplicates_found.append(canonical)
                else:
                    gen_keys.add(key)
                    gen_canonical.append(canonical)
                    
        # Calculate overlap metrics
        overlap = [s for s in gen_canonical if get_skill_key(s) in auth_keys]
        missing_auth = [s for s in auth_canonical if get_skill_key(s) not in gen_keys]
        unsupported_gen = [s for s in gen_canonical if get_skill_key(s) not in auth_keys]
        
        overlap_ratio = len(overlap) / len(auth_canonical) if auth_canonical else 1.0
        fit_metrics = calculate_relevance_metrics(profile)
        career_fit_score = fit_metrics["career_fit_score"]
        
        # 5. Check data quality issues
        is_data_issue = False
        data_issue_reason = ""
        if not ck_name:
            is_data_issue = True
            data_issue_reason = "No matching Career Knowledge record found in database."
        elif len(auth_canonical) < 3:
            is_data_issue = True
            data_issue_reason = f"Career Knowledge has only {len(auth_canonical)} skills ({', '.join(auth_canonical)}), which is insufficient reference data."
            
        # 6. Check quality/correctness concerns
        warnings = []
        
        # Check duplicate skills
        if duplicates_found:
            warnings.append(f"Duplicate concepts in generated profile: {', '.join(duplicates_found)}")
            
        # Check vague skills
        vague_found = [s for s in all_gen_skills if get_skill_key(s) in VAGUE_SKILLS]
        if vague_found:
            warnings.append(f"Vague/generic skills: {', '.join(vague_found)}")
            
        # Check out-of-domain or generic fallback issues
        if role == "AI Engineer":
            # AI Engineer should not inherit web frontend skills (like JavaScript) or standard cloud unless justified
            web_skills = {"javascript", "html", "css", "webassembly", "wasm"}
            ai_web_contam = [s for s in all_gen_skills if get_skill_key(s) in web_skills]
            if ai_web_contam:
                warnings.append(f"AI Engineer profile contains web/frontend skills: {', '.join(ai_web_contam)}")
                
        elif role == "DevOps Engineer":
            # DevOps should not inherit generic backend web development skills
            backend_skills = {"django", "flask", "express", "nodejs", "spring"}
            devops_contam = [s for s in all_gen_skills if get_skill_key(s) in backend_skills]
            if devops_contam:
                warnings.append(f"DevOps profile contains backend web skills: {', '.join(devops_contam)}")
                
        # Determine status
        if is_data_issue:
            status = "DATA ISSUE"
            status_reason = data_issue_reason
        elif warnings:
            status = "REGENERATE"
            status_reason = "; ".join(warnings)
        elif career_fit_score < 0.30:
            status = "REGENERATE"
            status_reason = f"Career Fit Score {career_fit_score:.2f} is below threshold 0.30."
        else:
            status = "PASS"
            status_reason = "Competency profile represents minimum required skills with high domain alignment."
            
        log(f"Cache HIT/MISS: {'HIT' if metrics.get('cache_hit') else 'MISS'}")
        log(f"Generation time: {t_duration:.2f}s")
        log(f"Career Fit Score: {career_fit_score:.2f}")
        log(f"Authoritative skills count: {len(auth_canonical)}")
        log(f"Authoritative skills: {', '.join(auth_canonical) if auth_canonical else 'None'}")
        log(f"Generated skills: {', '.join(gen_canonical)}")
        log(f"Overlap: {', '.join(overlap) if overlap else 'None'}")
        log(f"Missing Authoritative skills: {', '.join(missing_auth) if missing_auth else 'None'}")
        log(f"Generated-but-unsupported skills: {', '.join(unsupported_gen) if unsupported_gen else 'None'}")
        log(f"Overlap ratio: {overlap_ratio:.2f}")
        
        if profile.truncated_skills:
            log(f"Truncated skills: {', '.join(profile.truncated_skills)}")
            
        log(f"STATUS: {status}")
        log(f"Reason: {status_reason}")
        
        # Log by tier
        for tier_name, skills in gen_by_tier.items():
            req_status = "Required" if tier_name in ("Foundation", "Core Domain") else "Optional"
            log(f"  {tier_name} ({len(skills)} skills) [Required/Optional: {req_status}]:")
            for skill in skills:
                log(f"    - {skill}")

    out_dir = "/home/dev/.gemini/antigravity/brain/ee143111-8694-4be1-81fa-1b497778a9f8/scratch"
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "audit_output.txt"), "w") as f:
        f.write("\n".join(output_lines))
    log(f"\nAudit output written to {out_dir}/audit_output.txt")

if __name__ == "__main__":
    run_audit()
