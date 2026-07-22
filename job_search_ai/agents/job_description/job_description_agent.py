"""
JobDescriptionAgent — single public entry point for job description generation.

Execution flow
--------------
     
  Role
    │
    ▼  Stage 1 — JDKnowledgeRetriever  (vector search → Qdrant, dedicated
    │             "<collection>_job_description" collection)
    │
    ├─── Knowledge HIT (similarity ≥ threshold) ──► Evidence ──► PromptBuilder ──► LLM
    │
    └─── Knowledge MISS
              │
              ▼  QueryBuilder → TavilyService (reused from career_trend) → ResultFilter
              │
              ▼  JDKnowledgeBuilder
              │     One LLM call extracts a structured RoleProfile from the
              │     filtered search results, embeds it, and upserts it into
              │     Qdrant. Returns the profile directly — no re-read.
              │
              ▼  Evidence ──► PromptBuilder ──► LLM (final JD)

Key invariants (same pattern as CareerTrendAgent)
--------------------------------------------------
  - Exactly ONE "final" LLM call produces the returned JobDescriptionResponse.
    (MISS path adds one extra extraction LLM call inside JDKnowledgeBuilder,
    same as CareerTrendAgent's KnowledgeBuilder does for career profiles.)
  - MISS path never re-reads Qdrant after JDKnowledgeBuilder persists.
  - PromptBuilder only receives structured Evidence — never raw search results.
  - The caller always receives a response even if Qdrant persistence fails.
"""

from __future__ import annotations

import logging
import time

from job_search_ai.agents.career_trend.result_filter import ResultFilter
from job_search_ai.agents.career_trend.tavily_service import TavilyService
from job_search_ai.agents.job_description.knowledge_builder import BuildResult, JDKnowledgeBuilder
from job_search_ai.agents.job_description.knowledge_retrival import JDKnowledgeRetriever
from job_search_ai.agents.job_description.llm_service import LLMService, LLMServiceError
from job_search_ai.agents.job_description.prompt_builder import Evidence, PromptBuilder
from job_search_ai.agents.job_description.query_builder import QueryBuilder
from job_search_ai.agents.job_description.schemas import JobDescriptionRequest, JobDescriptionResponse

logger = logging.getLogger(__name__)


class JobDescriptionAgentError(Exception):
    """Raised when the JobDescriptionAgent pipeline fails at any stage."""


class JobDescriptionAgent:

    def run(self, request: JobDescriptionRequest) -> JobDescriptionResponse:
        logger.info(
            "JobDescriptionAgent starting — role=%r seniority=%r department=%r",
            request.role, request.seniority, request.department,
        )
        t_total = time.perf_counter()

        # ------------------------------------------------------------------
        # Stage 0 — Settings (shared with CareerTrendAgent)
        # ------------------------------------------------------------------
        from job_search_ai.services.settings_service import SettingsService
        settings = SettingsService.get()
        threshold = float(settings.similarity_threshold or 0.75)

        # ------------------------------------------------------------------
        # Stage 1 — JDKnowledgeRetriever
        # ------------------------------------------------------------------
        t = time.perf_counter()
        retrieved = self._retrieve(request, settings)
        t_retrieval = time.perf_counter() - t

        good = [p for p in retrieved if p.similarity >= threshold]
        tavily_used = knowledge_updated = False
        t_search = t_filter = t_build = 0.0

        if good:
            # ── Knowledge HIT ──────────────────────────────────────────
            logger.info("JobDescriptionAgent: Knowledge HIT — %d ≥ %.2f — skipping Tavily",
                        len(good), threshold)
            profiles = good
            knowledge_hit = True

        else:
            # ── Knowledge MISS ─────────────────────────────────────────
            knowledge_hit = False
            logger.info("JobDescriptionAgent: Knowledge MISS — running Tavily pipeline")

            # Stage 2 — QueryBuilder
            queries = self._build_queries(request)

            # Stage 3 — Tavily search
            t = time.perf_counter()
            raw_results = self._search(queries)
            t_search = time.perf_counter() - t
            tavily_used = True

            # Stage 4 — ResultFilter
            t = time.perf_counter()
            filtered = self._filter(raw_results)
            t_filter = time.perf_counter() - t

            # Stage 5 — JDKnowledgeBuilder (extract + embed + persist)
            t = time.perf_counter()
            build_result = self._build_profile(request, filtered, settings)
            t_build = time.perf_counter() - t

            if build_result.profiles:
                knowledge_updated = build_result.is_new
                profiles = build_result.profiles
            elif retrieved:
                # Nothing new built — fall back to whatever the retriever
                # found, even if it was below the HIT threshold.
                logger.warning("JobDescriptionAgent: extraction produced nothing — "
                                "falling back to %d below-threshold cached profiles",
                                len(retrieved))
                profiles = retrieved
            else:
                raise JobDescriptionAgentError(
                    "No role knowledge available in cache and web extraction failed."
                )

        # ------------------------------------------------------------------
        # Stage 6 — Evidence + PromptBuilder
        # ------------------------------------------------------------------
        evidence = Evidence.from_profiles(profiles[:3])

        t = time.perf_counter()
        prompt = PromptBuilder().build(
            request, evidence,
            max_chars=int(settings.maximum_prompt_characters or 4000),
        )
        t_prompt = time.perf_counter() - t

        # ------------------------------------------------------------------
        # Stage 7 — Final LLM call
        # ------------------------------------------------------------------
        t = time.perf_counter()
        response = self._generate(prompt, request)
        t_llm = time.perf_counter() - t

        total_time = time.perf_counter() - t_total

        response.metrics = {
            "knowledge_hit": knowledge_hit,
            "knowledge_count": len(retrieved),
            "tavily_used": tavily_used,
            "knowledge_updated": knowledge_updated,
            "retrieval_time": round(t_retrieval, 3),
            "search_time": round(t_search, 3),
            "filter_time": round(t_filter, 3),
            "kb_build_time": round(t_build, 3),
            "prompt_time": round(t_prompt, 3),
            "prompt_length": len(prompt),
            "llm_time": round(t_llm, 3),
            "total_time": round(total_time, 3),
        }

        logger.info(
            "JobDescriptionAgent finished — role=%r hit=%s tavily=%s total=%.2fs",
            request.role, knowledge_hit, tavily_used, total_time,
        )
        return response

    # ------------------------------------------------------------------
    # Stage runners
    # ------------------------------------------------------------------

    def _retrieve(self, request: JobDescriptionRequest, settings) -> list:
        try:
            return JDKnowledgeRetriever(settings).retrieve(request)
        except Exception as exc:  # noqa: BLE001
            logger.warning("JobDescriptionAgent: retrieval failed (%s) — treating as MISS", exc)
            return []

    def _build_queries(self, request: JobDescriptionRequest) -> list[str]:
        try:
            return QueryBuilder().build(request)
        except Exception as exc:
            raise JobDescriptionAgentError(f"QueryBuilder failed: {exc}") from exc

    def _search(self, queries: list[str]) -> list:
        try:
            return TavilyService().search(queries)
        except Exception as exc:
            raise JobDescriptionAgentError(f"TavilyService failed: {exc}") from exc

    def _filter(self, raw_results: list) -> list:
        try:
            return ResultFilter().filter(raw_results)
        except Exception as exc:
            raise JobDescriptionAgentError(f"ResultFilter failed: {exc}") from exc

    def _build_profile(self, request: JobDescriptionRequest, filtered: list, settings) -> BuildResult:
        try:
            return JDKnowledgeBuilder(settings).build(request, filtered)
        except Exception as exc:  # noqa: BLE001
            # Best-effort, matches CareerTrendAgent's invariant.
            logger.warning("JobDescriptionAgent: JDKnowledgeBuilder failed (%s)", exc)
            return BuildResult(is_new=False, profiles=[])

    def _generate(self, prompt: str, request: JobDescriptionRequest) -> JobDescriptionResponse:
        try:
            return LLMService().generate(prompt, request)
        except LLMServiceError as exc:
            raise JobDescriptionAgentError(f"LLMService failed: {exc}") from exc
        except Exception as exc:
            raise JobDescriptionAgentError(f"Unexpected error in LLMService: {exc}") from exc