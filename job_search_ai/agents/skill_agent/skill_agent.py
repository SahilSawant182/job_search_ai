"""
SkillAgent — generates the three skill tiers for a role and (optionally)
saves them into the "Job Description" doctype.

Execution flow
--------------

  Role
    │
    ▼  SkillKnowledgeCache.lookup()  (Qdrant vector search — dedicated
    │                                  "<collection>_skill_cache" collection)
    │
    ├─── Cache HIT (similarity ≥ threshold) ──► use cached tiers
    │
    └─── Cache MISS
              ▼  LLMService.generate_skills()   (ONE direct LLM call,
              │                                   no Tavily / web search)
              ▼  SkillKnowledgeCache.store()     (embed + upsert for next time)

  ▼  optional: doctype_writer.save_job_description()  → "Job Description" doc

Key invariants
--------------
  - No web search anywhere in this agent — skills come from the model's own
    knowledge, or from the Qdrant cache.
  - Exactly ONE LLM call per request (only on cache MISS).
  - Cache write is best-effort: a Qdrant failure never blocks the response.
"""

from __future__ import annotations

import logging
import time

from job_search_ai.agents.skill_agent.knowledge_cache import SkillKnowledgeCache
from job_search_ai.agents.skill_agent.llm_service import LLMService, LLMServiceError
from job_search_ai.agents.skill_agent.schemas import SkillProfile, SkillRequest, SkillResult

logger = logging.getLogger(__name__)


class SkillAgentError(Exception):
    """Raised when the SkillAgent pipeline fails."""


class SkillAgent:

    def run(self, request: SkillRequest, save_to_doctype: bool = True) -> SkillResult:
        logger.info("SkillAgent starting — role=%r seniority=%r", request.role, request.seniority)
        t_total = time.perf_counter()

        from job_search_ai.services.settings_service import SettingsService
        settings = SettingsService.get()
        threshold = float(settings.similarity_threshold or 0.75)

        cache = SkillKnowledgeCache(settings)

        # ------------------------------------------------------------------
        # Stage 1 — cache lookup
        # ------------------------------------------------------------------
        t = time.perf_counter()
        cached = self._safe_lookup(cache, request)
        t_lookup = time.perf_counter() - t

        cache_hit = bool(cached and cached.similarity >= threshold)

        if cache_hit:
            logger.info("SkillAgent: cache HIT (similarity=%.3f ≥ %.2f) for role=%r",
                        cached.similarity, threshold, request.role)
            profile = cached
            t_llm = 0.0
        else:
            logger.info("SkillAgent: cache MISS — generating via LLM (role=%r)", request.role)
            t = time.perf_counter()
            profile = self._generate(request)
            t_llm = time.perf_counter() - t

            # Best-effort cache write, never blocks the response.
            self._safe_store(cache, profile)

        # ------------------------------------------------------------------
        # Optional: persist to the "Job Description" doctype
        # ------------------------------------------------------------------
        doc_name = None
        if save_to_doctype:
            try:
                from job_search_ai.agents.skill_agent.doctype_writer import save_job_description
                doc_name = save_job_description(profile)
            except Exception as exc:  # noqa: BLE001
                # Don't fail the whole request just because the doctype save failed —
                # the caller still gets the generated skills back.
                logger.warning("SkillAgent: failed to save Job Description doc (%s)", exc)

        total_time = time.perf_counter() - t_total

        result = SkillResult(
            profile=profile,
            doc_name=doc_name,
            metrics={
                "cache_hit": cache_hit,
                "lookup_time": round(t_lookup, 3),
                "llm_time": round(t_llm, 3),
                "total_time": round(total_time, 3),
            },
        )
        logger.info("SkillAgent finished — role=%r cache_hit=%s doc_name=%r total=%.2fs",
                    request.role, cache_hit, doc_name, total_time)
        return result

    # ------------------------------------------------------------------
    # Stage runners
    # ------------------------------------------------------------------

    def _safe_lookup(self, cache: SkillKnowledgeCache, request: SkillRequest) -> SkillProfile | None:
        try:
            return cache.lookup(request.role, request.seniority)
        except Exception as exc:  # noqa: BLE001
            logger.warning("SkillAgent: cache lookup failed (%s) — treating as MISS", exc)
            return None

    def _generate(self, request: SkillRequest) -> SkillProfile:
        import re
        DUMMY_SKILL_RE = re.compile(r"^(skill\d+|unknown|n/a|placeholder|none)$", re.IGNORECASE)

        def sanitize(skill_list: list[str]) -> list[str]:
            return [s for s in skill_list if s and not DUMMY_SKILL_RE.match(s.strip())]

        try:
            llm = LLMService()
            skills = llm.generate_skills(request.role, request.seniority)
        except LLMServiceError as exc:
            raise SkillAgentError(f"LLMService failed: {exc}") from exc

        return SkillProfile(
            role_name=request.role,
            foundation_skills=sanitize(skills["foundation_skills"]),
            core_domain_skills=sanitize(skills["core_domain_skills"]),
            industry_skills=sanitize(skills["industry_skills"]),
            emerging_skills=sanitize(skills["emerging_skills"]),
            similarity=1.0,
            source="llm",
        )

    def _safe_store(self, cache: SkillKnowledgeCache, profile: SkillProfile) -> None:
        try:
            cache.store(profile)
        except Exception as exc:  # noqa: BLE001
            logger.warning("SkillAgent: cache store failed (%s)", exc)