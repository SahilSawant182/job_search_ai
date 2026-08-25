import logging
import frappe
from job_search_ai.agents.skill_agent.schemas import SkillProfile
from job_search_ai.services.skill_gap.normalizer import parse_skill_string, get_skill_key

logger = logging.getLogger(__name__)

# Enforced count limits for skill tiers
FOUNDATION_LIMIT = 6
CORE_DOMAIN_LIMIT = 8
INDUSTRY_LIMIT = 5
EMERGING_LIMIT = 3

# Minimum relevance career fit score threshold
RELEVANCE_THRESHOLD = 0.30

# Contrasting competency domain groups for out-of-domain check
DOMAINS = [
    {"frontend", "front-end", "web designer", "digital designer"},
    {"backend", "devops", "cloud", "systems administrator", "infrastructure"},
    {"ai", "machine learning", "data scientist", "data analyst", "deep learning", "researcher"},
    {"frappe", "erpnext"}
]

# Skills that a Frontend Developer profile must NOT contain unless explicitly allowed
FRONTEND_BLOCKED_SKILLS = {
    "expressjs", "express", "mongoose", "mongodb", "nodejs", "node", "kubernetes", "terraform",
    "docker", "ansible", "prometheus", "grafana", "jenkins", "cicd", "ci/cd",
    "postgresql", "mysql", "mariadb", "redis", "kafka", "hadoop", "spark", "cassandra",
    "django", "flask", "fastapi", "springboot", "spring boot", "laravel", "rails", "ruby on rails"
}

# Common cross-domain baseline skills that are NEVER counted as out-of-domain
COMMON_ALLOWLIST = {
    "git", "github", "githubactions", "python", "sql", "linux", "html", "css", "javascript",
    "restfulapi", "restfulapis", "docker", "aws", "amazonwebservices", "gcp", "googlecloudplatform",
    "azure", "api", "apis", "databases", "database", "cloud", "cloudcomputing"
}

def is_frontend_role(role: str) -> bool:
    role_lower = (role or "").lower()
    return "frontend" in role_lower or "front-end" in role_lower or "web designer" in role_lower

def get_career_group_indices(role_name: str) -> set[int]:
    """
    Find which domain groups the role name matches.
    """
    role_lower = (role_name or "").lower()
    matched = set()
    for idx, domain_set in enumerate(DOMAINS):
        for term in domain_set:
            if term in role_lower:
                matched.add(idx)
                break
    return matched

def get_career_knowledge_skills(role_name: str) -> set[str]:
    """
    Query Career Knowledge to get allowed skills for the role.
    """
    valid_skills = set()
    if not getattr(frappe, "db", None):
        return valid_skills

    from job_search_ai.agents.skill_agent.doctype_writer import _resolve_job_profile
    try:
        ck_name = _resolve_job_profile(role_name)
        if ck_name:
            skills = frappe.db.sql(
                "SELECT skill_name FROM `tabCareer Knowledge Skill` WHERE parent = %s",
                (ck_name,),
                as_dict=True
            )
            for s in skills:
                name = s.get("skill_name")
                if name:
                    valid_skills.add(get_skill_key(name))
    except Exception as e:
        logger.warning("Validator: Failed to load Career Knowledge skills for %r: %s", role_name, e)

    return valid_skills

def calculate_relevance_metrics(profile: SkillProfile) -> dict:
    """
    Computes career-specific relevance metrics.
    """
    import frappe
    from job_search_ai.agents.skill_agent.doctype_writer import _resolve_job_profile

    # Collect all generated skill keys
    all_gen_skills = (
        profile.foundation_skills +
        profile.core_domain_skills +
        profile.industry_skills +
        profile.emerging_skills
    )
    gen_keys = {get_skill_key(s) for s in all_gen_skills if s}

    # Load target career skills
    target_ck_keys = set()
    ck_name = _resolve_job_profile(profile.role_name)
    if ck_name:
        skills = frappe.db.sql(
            "SELECT skill_name FROM `tabCareer Knowledge Skill` WHERE parent = %s",
            (ck_name,),
            as_dict=True
        )
        target_ck_keys = {get_skill_key(s["skill_name"]) for s in skills if s.get("skill_name")}

    # Get target groups to filter out-of-domain skills
    target_groups = get_career_group_indices(profile.role_name)

    # Load contrasting careers' skills to check out-of-domain
    other_ck_keys = set()
    if getattr(frappe, "db", None):
        all_ck_records = frappe.get_all("Career Knowledge", fields=["name", "career_name"])
        for record in all_ck_records:
            if record.name == ck_name:
                continue
            
            # Check if this other career belongs to a contrasting domain group
            other_groups = get_career_group_indices(record.career_name)
            
            # If target groups exist and there is an intersection, it is NOT contrasting
            if target_groups and other_groups and target_groups.intersection(other_groups):
                continue
                
            skills = frappe.db.sql(
                "SELECT skill_name FROM `tabCareer Knowledge Skill` WHERE parent = %s",
                (record.name,),
                as_dict=True
            )
            for s in skills:
                name = s.get("skill_name")
                if name:
                    other_ck_keys.add(get_skill_key(name))

    # Calculate overlap and out-of-domain
    overlap_keys = gen_keys.intersection(target_ck_keys)
    
    # Out of domain keys: generated keys that are NOT in target CK, but are in contrasting CKs, and not in the common allowlist
    out_of_domain_keys = (gen_keys - target_ck_keys).intersection(other_ck_keys) - COMMON_ALLOWLIST

    overlap_count = len(overlap_keys)
    out_of_domain_count = len(out_of_domain_keys)

    overlap_ratio_wrt_ck = (overlap_count / len(target_ck_keys)) if len(target_ck_keys) > 0 else 1.0
    overlap_ratio_wrt_gen = (overlap_count / len(gen_keys)) if len(gen_keys) > 0 else 1.0
    out_of_domain_ratio = (out_of_domain_count / len(gen_keys)) if len(gen_keys) > 0 else 0.0

    # Calculate career fit score
    if len(target_ck_keys) == 0:
        career_fit_score = 1.0
    else:
        career_fit_score = overlap_ratio_wrt_ck * (1.0 - out_of_domain_ratio)

    overlap_skills = [s for s in all_gen_skills if get_skill_key(s) in overlap_keys]
    out_of_domain_skills = [s for s in all_gen_skills if get_skill_key(s) in out_of_domain_keys]

    return {
        "generated_skill_count": len(gen_keys),
        "career_known_skill_count": len(target_ck_keys),
        "overlap_count": overlap_count,
        "overlap_ratio_wrt_ck": overlap_ratio_wrt_ck,
        "overlap_ratio_wrt_gen": overlap_ratio_wrt_gen,
        "out_of_domain_count": out_of_domain_count,
        "out_of_domain_ratio": out_of_domain_ratio,
        "career_fit_score": career_fit_score,
        "overlap_skills": overlap_skills,
        "out_of_domain_skills": out_of_domain_skills,
    }

def validate_and_normalize_profile(profile: SkillProfile, truncate_excess: bool = False) -> bool:
    """
    Normalizes, deduplicates, and validates a SkillProfile.
    Modifies the profile in-place to contain fully canonicalized/deduplicated lists.
    Returns True if valid. Raises ValueError on failure.
    """
    # 1. Canonicalization (normalization + decomposition)
    foundation = parse_skill_string(profile.foundation_skills)
    core = parse_skill_string(profile.core_domain_skills)
    industry = parse_skill_string(profile.industry_skills)
    emerging = parse_skill_string(profile.emerging_skills)

    # 2. Duplicate Removal & Cross-tier Deduplication
    seen_keys = set()
    
    def dedup_tier(skills_list: list[str]) -> list[str]:
        result = []
        for s in skills_list:
            k = get_skill_key(s)
            if k and k not in seen_keys:
                seen_keys.add(k)
                result.append(s)
        return result

    profile.foundation_skills = dedup_tier(foundation)
    profile.core_domain_skills = dedup_tier(core)
    profile.industry_skills = dedup_tier(industry)
    profile.emerging_skills = dedup_tier(emerging)

    # 3. Count Validation (No silent truncation!)
    if len(profile.foundation_skills) > FOUNDATION_LIMIT:
        if truncate_excess:
            excess = profile.foundation_skills[FOUNDATION_LIMIT:]
            logger.warning("Truncating excess foundation skills from %d to %d: %s", len(profile.foundation_skills), FOUNDATION_LIMIT, excess)
            profile.truncated_skills.extend(excess)
            profile.foundation_skills = profile.foundation_skills[:FOUNDATION_LIMIT]
        else:
            raise ValueError(
                f"Foundation skills count {len(profile.foundation_skills)} exceeds limit of {FOUNDATION_LIMIT}"
            )
    if len(profile.core_domain_skills) > CORE_DOMAIN_LIMIT:
        if truncate_excess:
            excess = profile.core_domain_skills[CORE_DOMAIN_LIMIT:]
            logger.warning("Truncating excess core domain skills from %d to %d: %s", len(profile.core_domain_skills), CORE_DOMAIN_LIMIT, excess)
            profile.truncated_skills.extend(excess)
            profile.core_domain_skills = profile.core_domain_skills[:CORE_DOMAIN_LIMIT]
        else:
            raise ValueError(
                f"Core Domain skills count {len(profile.core_domain_skills)} exceeds limit of {CORE_DOMAIN_LIMIT}"
            )
    if len(profile.industry_skills) > INDUSTRY_LIMIT:
        if truncate_excess:
            excess = profile.industry_skills[INDUSTRY_LIMIT:]
            logger.warning("Truncating excess industry skills from %d to %d: %s", len(profile.industry_skills), INDUSTRY_LIMIT, excess)
            profile.truncated_skills.extend(excess)
            profile.industry_skills = profile.industry_skills[:INDUSTRY_LIMIT]
        else:
            raise ValueError(
                f"Industry skills count {len(profile.industry_skills)} exceeds limit of {INDUSTRY_LIMIT}"
            )
    if len(profile.emerging_skills) > EMERGING_LIMIT:
        if truncate_excess:
            excess = profile.emerging_skills[EMERGING_LIMIT:]
            logger.warning("Truncating excess emerging skills from %d to %d: %s", len(profile.emerging_skills), EMERGING_LIMIT, excess)
            profile.truncated_skills.extend(excess)
            profile.emerging_skills = profile.emerging_skills[:EMERGING_LIMIT]
        else:
            raise ValueError(
                f"Emerging skills count {len(profile.emerging_skills)} exceeds limit of {EMERGING_LIMIT}"
            )

    # 4. Role-specific validation (Contamination Check)
    if is_frontend_role(profile.role_name):
        valid_skills = get_career_knowledge_skills(profile.role_name)
        
        all_skills = (
            profile.foundation_skills +
            profile.core_domain_skills +
            profile.industry_skills +
            profile.emerging_skills
        )
        
        for skill in all_skills:
            key = get_skill_key(skill)
            
            is_blocked = False
            if key in FRONTEND_BLOCKED_SKILLS:
                is_blocked = True
            else:
                for blocked in FRONTEND_BLOCKED_SKILLS:
                    if len(blocked) > 3 and blocked in key:
                        is_blocked = True
                        break
            
            if is_blocked:
                allowed = False
                if key in valid_skills:
                    allowed = True
                else:
                    for vs in valid_skills:
                        if vs == key or vs in key or key in vs:
                            allowed = True
                            break
                if not allowed:
                    raise ValueError(
                        f"Frontend role contaminated with backend/DevOps skill: '{skill}'"
                    )

    # 5. Career-specific relevance validator (Career Fit Score)
    metrics = calculate_relevance_metrics(profile)
    if metrics["career_fit_score"] < RELEVANCE_THRESHOLD:
        raise ValueError(
            f"Profile career fit score {metrics['career_fit_score']:.2f} is below relevance threshold of {RELEVANCE_THRESHOLD}. "
            f"Overlap skills: {metrics['overlap_skills']}. Out-of-domain skills: {metrics['out_of_domain_skills']}."
        )

    return True
