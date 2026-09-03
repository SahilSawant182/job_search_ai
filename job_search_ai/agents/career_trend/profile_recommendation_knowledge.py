# -*- coding: utf-8 -*-
"""
ProfileRecommendationKnowledge — domain-aware profile-level caching.

v3 Changes
----------
- Stores `academic_domain`, `branch_family`, `degree_family` alongside
  interests/skills so that lookup can reject domain-incompatible HIT candidates
  (e.g. a Cybersecurity profile cannot reuse a Data Engineering cache entry).
- Domain compatibility is a MANDATORY guard on top of vector + structured similarity.
- Compatible domain families are defined in _DOMAIN_COMPAT below — groups of
  academically adjacent branches that may share career recommendations.
"""
import logging
import uuid
import requests
from datetime import datetime, timezone
from job_search_ai.agents.career_trend.schemas import StudentProfile, CareerTrendResponse
from job_search_ai.services.ai.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)

REC_COLLECTION_SUFFIX = "_profile_rec_knowledge"

# ──────────────────────────────────────────────────────────────────────────────
# DOMAIN COMPATIBILITY MODEL
# Each entry is a named family.  Profiles within the same family may share
# cached career-knowledge.  Profiles in different families MUST NOT.
#
# Rule: student_domain == cached_domain  →  domain-compatible  →  HIT allowed
#       otherwise                         →  domain-mismatch    →  MISS forced
# ──────────────────────────────────────────────────────────────────────────────
_DOMAIN_MAP: dict[str, str] = {
    # Technology
    "computer science": "technology",
    "computer engineering": "technology",
    "computer applications": "technology",
    "cse": "technology",
    "software engineering": "technology",
    "software development": "technology",
    "information technology": "technology",
    "data science": "technology",
    "artificial intelligence": "technology",
    "cybersecurity": "technology",
    "networking": "technology",
    "cloud computing": "technology",
    "devops": "technology",
    "web development": "technology",
    "mca": "technology",
    "b.tech": "technology",
    "btech": "technology",
    "m.tech": "technology",
    "b.e": "technology",
    # Engineering (non-CS)
    "mechanical engineering": "engineering",
    "civil engineering": "engineering",
    "electrical engineering": "engineering",
    "electronics engineering": "engineering",
    "chemical engineering": "engineering",
    "aerospace engineering": "engineering",
    "industrial engineering": "engineering",
    "production engineering": "engineering",
    "mechatronics": "engineering",
    "robotics": "engineering",
    "embedded systems": "engineering",
    # Business / Commerce
    "business administration": "business",
    "business management": "business",
    "bba": "business",
    "mba": "business",
    "commerce": "business",
    "marketing management": "business",
    "finance management": "business",
    "accounting": "business",
    "economics": "business",
    "entrepreneurship": "business",
    "operations management": "business",
    "supply chain management": "business",
    "human resources": "business",
    "sales management": "business",
    "banking": "business",
    # Science (non-engineering)
    "biology": "science",
    "chemistry": "science",
    "physics": "science",
    "mathematics": "science",
    "statistics": "science",
    "biotechnology": "science",
    "microbiology": "science",
    "biochemistry": "science",
    "agriculture": "science",
    "food technology": "science",
    "pharmacy": "science",
    "b.pharm": "science",
    "m.pharm": "science",
    "pharmacognosy": "science",
    "environmental science": "science",
    "b.pham": "science",
    "b.pharma": "science",
    # Healthcare / Medical / Allied Health
    "nursing": "healthcare",
    "mbbs": "healthcare",
    "bsc nursing": "healthcare",
    "clinical": "healthcare",
    "healthcare": "healthcare",
    "bhms": "healthcare",
    "bams": "healthcare",
    "bds": "healthcare",
    "bpth": "healthcare",
    "b.p.th": "healthcare",
    "physiotherapy": "healthcare",
    "occupational therapy": "healthcare",
    "homeopathy": "healthcare",
    "homoeopathy": "healthcare",
    "homoeopathic": "healthcare",
    "homeopathic": "healthcare",
    "ayurveda": "healthcare",
    "ayurvedic": "healthcare",
    "dental surgery": "healthcare",
    "naturopathy": "healthcare",
    "unani": "healthcare",
    "siddha": "healthcare",
    "materia medica": "healthcare",
    "paediatrics": "healthcare",
    "gynaecology": "healthcare",
    "radiology": "healthcare",
    "pathology": "healthcare",
    "ophthalmology": "healthcare",
    # Arts / Humanities / Social Sciences
    "psychology": "humanities",
    "sociology": "humanities",
    "political science": "humanities",
    "humanities": "humanities",
    "english literature": "humanities",
    "literature": "humanities",
    "philosophy": "humanities",
    "history": "humanities",
    "mass communication": "humanities",
    "journalism": "humanities",
    "social work": "humanities",
    # Creative / Design
    "design": "creative",
    "graphic design": "creative",
    "animation": "creative",
    "fashion design": "creative",
    "fine arts": "creative",
    "interaction design": "creative",
    "b.des": "creative",
    # Legal
    "law": "legal",
    "legal studies": "legal",
    "llb": "legal",
    # Education
    "education": "education",
    "b.ed": "education",
    "teaching": "education",
}

# Families that can share recommendations with each other
_COMPATIBLE_FAMILIES: dict[str, set[str]] = {
    "technology":  {"technology"},
    "engineering": {"engineering", "technology"},   # Tech cross-over is fine
    "business":    {"business"},
    "science":     {"science", "healthcare"},        # Biomedical / pharma overlap
    "healthcare":  {"healthcare", "science"},        # Medical + biotech overlap
    "humanities":  {"humanities"},
    "creative":    {"creative"},
    "legal":       {"legal"},
    "education":   {"education", "humanities"},
}


import re as _re

def _classify_domain(branch: str, degree: str) -> str:
    """
    Return the academic domain family for a (branch, degree) pair.

    Uses whole-word / whole-token matching to prevent short keywords like
    'cs', 'it', 'ba', 'ma' from matching inside longer words
    (e.g. 'cs' inside 'homoeopathics', 'it' inside 'Quality').
    Longer keyword matches always win over shorter ones.
    """
    combined = (branch + " " + degree).lower().strip()

    # Tokenise: keep alphanumeric runs and dots (for abbreviations like b.tech)
    tokens = set(_re.findall(r'[a-z][a-z0-9.]*', combined))

    best_family  = "unknown"
    best_len     = 0

    for keyword, family in _DOMAIN_MAP.items():
        kw = keyword.lower().strip()
        kw_len = len(kw)

        # Multi-word keywords: check as a substring of the full combined text
        # but ONLY after verifying the keyword starts/ends on a word boundary.
        if " " in kw:
            pattern = r'\b' + _re.escape(kw) + r'\b'
            if _re.search(pattern, combined) and kw_len > best_len:
                best_family = family
                best_len    = kw_len
        else:
            # Single-word / abbreviation: must appear as a complete token
            if kw in tokens and kw_len > best_len:
                best_family = family
                best_len    = kw_len

    return best_family


def _domains_compatible(student_domain: str, cached_domain: str) -> bool:
    """Return True iff cached profile's domain can serve the student's domain."""
    if student_domain == "unknown" or cached_domain == "unknown":
        return True   # Can't classify → don't block
    allowed = _COMPATIBLE_FAMILIES.get(student_domain, {student_domain})
    return cached_domain in allowed


class ProfileRecommendationKnowledge:
    def __init__(self, settings):
        self.settings = settings
        self.qdrant_url = settings.qdrant_url.rstrip("/")
        self.collection = (settings.qdrant_collection_name or "career_knowledge") + REC_COLLECTION_SUFFIX
        self.embedding_svc = EmbeddingService(settings)
        self.distance = settings.vector_distance or "Cosine"

    # ── public ────────────────────────────────────────────────────────────────

    def lookup(self, student: StudentProfile) -> dict | None:
        interests, skills = self._normalize_profile(student)
        student_domain = _classify_domain(student.branch, student.degree)

        query_str = self._query_text(interests, skills)
        try:
            vector = self.embedding_svc.embed(query_str)
        except Exception as exc:
            logger.warning("ProfileRecommendationKnowledge: embedding failed during lookup (%s)", exc)
            return None

        try:
            resp = requests.post(
                f"{self.qdrant_url}/collections/{self.collection}/points/search",
                json={"vector": vector, "limit": 10, "with_payload": True},
                timeout=15,
            )
            resp.raise_for_status()
            hits = resp.json().get("result", [])
        except Exception as exc:
            logger.warning("ProfileRecommendationKnowledge: Qdrant lookup search failed (%s)", exc)
            return None

        for hit in hits:
            score = hit.get("score", 0.0)
            if score < 0.80:
                continue

            payload = hit.get("payload", {})
            if "career_paths" not in payload:
                continue

            # ── Guard 0: Schema version — v2 records have no domain metadata
            #    and must be treated as cache misses to prevent domain bypass.
            schema_version = payload.get("schema_version", "v2")
            if schema_version == "v2":
                logger.info(
                    "ProfileRecommendationKnowledge: INVALIDATED v2 record (no domain metadata) — treating as MISS"
                )
                continue

            # ── Guard 1: Domain compatibility ─────────────────────────────
            cached_domain = payload.get("academic_domain", "unknown")
            if not _domains_compatible(student_domain, cached_domain):
                logger.info(
                    "ProfileRecommendationKnowledge: DOMAIN MISMATCH — student=%r cached=%r — skipping HIT",
                    student_domain, cached_domain,
                )
                continue

            # ── Guard 2: Structured skill + interest similarity ────────────
            cached_interests = {i.strip().lower() for i in payload.get("interests", []) if i.strip()}
            student_interests = {i.strip().lower() for i in interests if i.strip()}
            cached_skills    = {s.strip().lower() for s in payload.get("skills", []) if s.strip()}
            student_skills   = {s.strip().lower() for s in skills if s.strip()}

            interest_sim = _jaccard(student_interests, cached_interests)
            skill_sim    = _jaccard(student_skills, cached_skills)

            combined_sim = 0.5 * interest_sim + 0.5 * skill_sim
            if combined_sim < 0.65:
                logger.info(
                    "ProfileRecommendationKnowledge: low structured similarity (%.3f < 0.65) — skipping",
                    combined_sim,
                )
                continue

            logger.info(
                "ProfileRecommendationKnowledge: HIT (vec=%.3f, combined=%.3f, domain=%r→%r)",
                score, combined_sim, student_domain, cached_domain,
            )
            payload["avg_similarity_score"] = score
            payload["combined_similarity"]   = combined_sim
            return payload

        return None

    def store(self, student: StudentProfile, response: CareerTrendResponse) -> None:
        interests, skills = self._normalize_profile(student)

        if not interests and not skills:
            logger.warning("ProfileRecommendationKnowledge: not storing empty profile")
            return

        query_str = self._query_text(interests, skills)
        try:
            vector = self.embedding_svc.embed(query_str)
        except Exception as exc:
            logger.warning("ProfileRecommendationKnowledge: embedding failed during store (%s)", exc)
            return

        self._ensure_collection(len(vector))

        from job_search_ai.services.knowledge.constants import MIN_FINAL_SCORE
        min_conf = int(MIN_FINAL_SCORE * 100)

        if isinstance(response, list):
            rec_paths = response
        elif hasattr(response, "recommended_paths"):
            rec_paths = getattr(response, "recommended_paths", []) or []
        elif isinstance(response, dict):
            rec_paths = response.get("recommended_paths", []) or []
        else:
            rec_paths = []

        career_paths_payload = [
            {"career": getattr(r, "career", r.get("career") if isinstance(r, dict) else None), "historical_score": round(getattr(r, "confidence", r.get("confidence", 0) if isinstance(r, dict) else 0) / 100.0, 4)}
            for r in rec_paths
            if getattr(r, "career", r.get("career") if isinstance(r, dict) else None) and getattr(r, "confidence", r.get("confidence", 0) if isinstance(r, dict) else 0) >= min_conf
        ]
        if not career_paths_payload:
            logger.warning("ProfileRecommendationKnowledge: no valid career paths to store")
            return

        academic_domain = _classify_domain(student.branch, student.degree)

        point = {
            "id": str(uuid.uuid4()),
            "vector": vector,
            "payload": {
                "interests":       interests,
                "skills":          skills,
                "career_paths":    career_paths_payload,
                # Domain metadata — used by lookup to reject cross-domain reuse
                "academic_domain": academic_domain,
                "branch_family":   student.branch.strip().lower(),
                "degree_family":   student.degree.strip().lower(),
                "schema_version":  "v3",
                "created_at":      datetime.now(tz=timezone.utc).isoformat(),
                "updated_at":      datetime.now(tz=timezone.utc).isoformat(),
            },
        }

        try:
            requests.put(
                f"{self.qdrant_url}/collections/{self.collection}/points?wait=true",
                json={"points": [point]},
                timeout=15,
            )
            logger.info(
                "ProfileRecommendationKnowledge: stored (domain=%r, branch=%r)",
                academic_domain, student.branch,
            )
        except Exception as exc:
            logger.warning("ProfileRecommendationKnowledge: Qdrant store failed (%s)", exc)

    # ── private ───────────────────────────────────────────────────────────────

    def _normalize_profile(self, student: StudentProfile) -> tuple[list[str], list[str]]:
        interests = sorted({i.strip().lower() for i in student.interests if i.strip()})
        from job_search_ai.services.skill_gap.normalizer import normalize_skill
        skills = sorted({normalize_skill(s) for s in student.skills if s.strip()})
        return interests, skills

    def _query_text(self, interests: list[str], skills: list[str]) -> str:
        parts = []
        if interests:
            parts.append("interests: " + ", ".join(interests))
        if skills:
            parts.append("skills: " + ", ".join(skills))
        return " | ".join(parts) if parts else "empty"

    def _ensure_collection(self, dim: int) -> None:
        try:
            check = requests.get(f"{self.qdrant_url}/collections/{self.collection}", timeout=10)
            if check.status_code == 200:
                return
            requests.put(
                f"{self.qdrant_url}/collections/{self.collection}",
                json={"vectors": {"size": dim, "distance": self.distance}},
                timeout=15,
            )
            logger.info(
                "ProfileRecommendationKnowledge: created collection %r (dim=%d)", self.collection, dim
            )
        except Exception as exc:
            logger.warning("ProfileRecommendationKnowledge: could not ensure collection (%s)", exc)


def _jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    matches = 0
    for item_a in a:
        for item_b in b:
            if item_a in item_b or item_b in item_a:
                matches += 1
                break
    return matches / max(len(a), len(b))
