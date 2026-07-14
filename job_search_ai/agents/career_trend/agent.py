"""
CareerTrendAgent — the single public entry point for career trend analysis.

Execution flow
--------------

  Student
    │
    ▼  Stage 1 — KnowledgeRetriever  (vector search → MariaDB)
    │
    ├─── Knowledge HIT ──► Evidence.from_knowledge() ──► PromptBuilder ──► LLM
    │
    └─── Knowledge MISS
              │
              ▼  QueryBuilder → TavilyService → ResultFilter
              │
              ▼  KnowledgeBuilder  (persist to MariaDB + Qdrant)
              │   └── returns MergedCareerProfile objects directly
              │
              ▼  Evidence.from_knowledge(profiles)  ──► PromptBuilder ──► LLM

Key invariants
--------------
  - Exactly ONE LLM call per request.
  - MISS path never re-reads from MariaDB after KnowledgeBuilder persists.
  - KnowledgeRetriever is used only on the HIT path and the initial check.
  - PromptBuilder only receives structured knowledge — never raw search results.
  - The user always receives a response even if KB update fails.
"""

from __future__ import annotations

import logging
import time

from job_search_ai.agents.career_trend.llm_service import LLMService, LLMServiceError
from job_search_ai.agents.career_trend.prompt_builder import Evidence, PromptBuilder
from job_search_ai.agents.career_trend.query_builder import QueryBuilder
from job_search_ai.agents.career_trend.result_filter import ResultFilter
from job_search_ai.agents.career_trend.schemas import (
    CareerTrendResponse,
    StudentProfile,
)
from job_search_ai.agents.career_trend.student_context_builder import StudentContextBuilder
from job_search_ai.agents.career_trend.tavily_service import TavilyService

logger = logging.getLogger(__name__)


class CareerTrendAgent:
    """
    Orchestrates the full career trend analysis pipeline.

    Knowledge-First: attempts retrieval from the Career Knowledge database
    before falling back to the Tavily web search pipeline.
    """

    def run(self, student: StudentProfile) -> CareerTrendResponse:
        """
        Execute the Knowledge-First career trend analysis for a student.
        """
        logger.info(
            "CareerTrendAgent starting analysis — branch=%r  country=%r",
            student.branch,
            student.country,
        )

        t_total = time.perf_counter()

        # ------------------------------------------------------------------
        # Stage 0 — Load SettingsService (once, shared across stages)
        # ------------------------------------------------------------------
        from job_search_ai.services.settings_service import SettingsService
        settings = SettingsService.get()

        # ------------------------------------------------------------------
        # Stage 1 — KnowledgeRetriever (Knowledge-First)
        # ------------------------------------------------------------------
        t = time.perf_counter()
        retrieved, knowledge_hit, avg_similarity = self._retrieve_knowledge(student, settings)
        t_retrieval = time.perf_counter() - t

        tavily_used        = False
        knowledge_updated  = False
        filtered_results   = []
        queries:    list[str] = []
        raw_results: list    = []

        if knowledge_hit:
            # ── Knowledge HIT path ──────────────────────────────────────
            logger.info(
                "CareerTrendAgent: Knowledge HIT — %d records  avg_similarity=%.4f  "
                "skipping Tavily",
                len(retrieved), avg_similarity,
            )
            evidence = Evidence.from_knowledge(retrieved)
            t_search = t_filter = t_knowledge_build = 0.0

        else:
            # ── Knowledge MISS path — execute Tavily pipeline ───────────
            logger.info(
                "CareerTrendAgent: Knowledge MISS (retrieved=%d  avg_sim=%.4f) "
                "— executing Tavily pipeline",
                len(retrieved), avg_similarity,
            )

            # Stage 2 — QueryBuilder
            queries = self._build_queries(student)

            # Stage 3 — Tavily search
            t = time.perf_counter()
            raw_results = self._search(queries)
            t_search = time.perf_counter() - t
            tavily_used = True

            # Stage 4 — ResultFilter
            t = time.perf_counter()
            filtered_results = self._filter(raw_results)
            t_filter = time.perf_counter() - t

            # Stage 5 — KnowledgeBuilder: persist and get structured profiles back
            # No second DB read — profiles are returned directly from the builder.
            t = time.perf_counter()
            built_profiles = self._build_and_get_profiles(student, filtered_results)
            t_knowledge_build = time.perf_counter() - t

            if built_profiles:
                knowledge_updated = True
                evidence = Evidence.from_knowledge(built_profiles)
            else:
                knowledge_updated = False
                # Fallback: use raw search results as evidence (no structured KB)
                evidence = Evidence.from_search_results(filtered_results)

        # ------------------------------------------------------------------
        # Stage 6 — StudentContext (deterministic, always runs)
        # ------------------------------------------------------------------
        t = time.perf_counter()
        context = self._build_context(student)
        t_context = time.perf_counter() - t

        # ------------------------------------------------------------------
        # Stage 7 — PromptBuilder
        # ------------------------------------------------------------------
        t = time.perf_counter()
        prompt = self._build_prompt(student, evidence, context, is_kh=knowledge_hit)
        t_prompt = time.perf_counter() - t

        # ------------------------------------------------------------------
        # Stage 8 — LLM
        # ------------------------------------------------------------------
        t = time.perf_counter()
        llm_service = LLMService()
        response = self._generate_with_service(prompt, llm_service)
        t_llm = time.perf_counter() - t

        total_time = time.perf_counter() - t_total

        # ------------------------------------------------------------------
        # Metrics
        # ------------------------------------------------------------------
        prompt_len = len(prompt)
        est_tokens = prompt_len // 4

        logger.info(
            "\n"
            "============================================================\n"
            "  PERFORMANCE METRICS (Knowledge-First Pipeline)\n"
            "============================================================\n"
            "Knowledge Hit          : %s\n"
            "Knowledge Count        : %d\n"
            "Avg Similarity Score   : %.4f\n"
            "Tavily Used            : %s\n"
            "Knowledge Updated      : %s\n"
            "------------------------------------------------------------\n"
            "Stage Retrieval Time   : %.3f sec\n"
            "Stage Search Time      : %.3f sec\n"
            "Stage Filter Time      : %.3f sec\n"
            "Stage KB Build Time    : %.3f sec\n"
            "Stage Context Time     : %.3f sec\n"
            "Stage Prompt Time      : %.3f sec\n"
            "Stage LLM Time         : %.3f sec\n"
            "------------------------------------------------------------\n"
            "Prompt Length          : %d chars\n"
            "Estimated Tokens       : %d\n"
            "Model Name             : %s\n"
            "Total Execution Time   : %.3f sec\n"
            "============================================================",
            "YES" if knowledge_hit else "NO",
            len(retrieved),
            avg_similarity,
            "YES" if tavily_used else "NO",
            "YES" if knowledge_updated else "NO",
            t_retrieval,
            t_search if tavily_used else 0.0,
            t_filter  if tavily_used else 0.0,
            t_knowledge_build if tavily_used else 0.0,
            t_context,
            t_prompt,
            t_llm,
            prompt_len,
            est_tokens,
            llm_service.model_name,
            total_time,
        )

        response.metrics = {
            # Knowledge-First metrics
            "knowledge_hit":          knowledge_hit,
            "knowledge_count":        len(retrieved),
            "avg_similarity_score":   avg_similarity,
            "tavily_used":            tavily_used,
            "knowledge_updated":      knowledge_updated,
            # Legacy metrics (kept for API compatibility)
            "query_count":            len(queries) if not knowledge_hit else 0,
            "parallel_search_time":   t_search if tavily_used else 0.0,
            "raw_results_count":      len(raw_results) if tavily_used else 0,
            "filtered_results_count": len(filtered_results),
            "placement_readiness":    context.placement_readiness,
            "recommendation_horizon": context.recommendation_horizon,
            "prompt_length":          prompt_len,
            "estimated_tokens":       est_tokens,
            "model_name":             llm_service.model_name,
            "llm_response_time":      t_llm,
            "total_execution_time":   total_time,
        }

        logger.info(
            "CareerTrendAgent finished — %d recommendations  knowledge_hit=%s  tavily_used=%s",
            len(response.recommended_paths), knowledge_hit, tavily_used,
        )
        return response

    # ------------------------------------------------------------------
    # Stage runners
    # ------------------------------------------------------------------

    def _retrieve_knowledge(
        self,
        student: StudentProfile,
        settings,
    ) -> tuple[list, bool, float]:
        """Run KnowledgeRetriever and determine whether we have a cache hit.

        Returns
        -------
        (retrieved, knowledge_hit, avg_similarity)
        """
        try:
            from job_search_ai.services.knowledge.knowledge_retriever import KnowledgeRetriever
            retriever = KnowledgeRetriever(settings=settings)
            retrieved = retriever.retrieve(student)
        except Exception as exc:
            logger.warning(
                "CareerTrendAgent: KnowledgeRetriever failed (%s) — falling back to Tavily",
                exc,
            )
            return [], False, 0.0

        if not retrieved:
            return [], False, 0.0

        avg_similarity = sum(r.similarity for r in retrieved) / len(retrieved)
        threshold      = settings.similarity_threshold

        # A Knowledge HIT means we found at least one high-quality record.
        # We do NOT require a minimum count — 1 excellent match is better than
        # 3 mediocre ones. Quality over quantity.
        knowledge_hit = len(retrieved) >= 1 and avg_similarity >= threshold

        logger.info(
            "KnowledgeRetriever: retrieved=%d  avg_sim=%.4f  "
            "threshold=%.2f  hit=%s",
            len(retrieved), avg_similarity, threshold, knowledge_hit,
        )
        return retrieved, knowledge_hit, avg_similarity

    def _build_queries(self, student: StudentProfile) -> list[str]:
        logger.info("CareerTrendAgent: Stage — QueryBuilder")
        try:
            queries = QueryBuilder().build(student)
            logger.info("QueryBuilder: %d queries built", len(queries))
            return queries
        except Exception as exc:
            raise CareerTrendAgentError(f"QueryBuilder failed: {exc}") from exc

    def _search(self, queries: list[str]) -> list:
        logger.info("CareerTrendAgent: Stage — Tavily parallel search")
        try:
            results = TavilyService().search(queries)
            logger.info("TavilyService: %d raw results retrieved", len(results))
            return results
        except Exception as exc:
            raise CareerTrendAgentError(f"TavilyService failed: {exc}") from exc

    def _filter(self, raw_results: list) -> list:
        logger.info("CareerTrendAgent: Stage — ResultFilter")
        try:
            filtered = ResultFilter().filter(raw_results)
            logger.info("ResultFilter: %d results after filtering", len(filtered))
            return filtered
        except Exception as exc:
            raise CareerTrendAgentError(f"ResultFilter failed: {exc}") from exc

    def _build_and_get_profiles(self, student: StudentProfile, filtered_results: list) -> list:
        """
        Run KnowledgeBuilder on the MISS path.

        Returns a list of MergedCareerProfile objects that can be passed directly
        to Evidence.from_knowledge().  The database has already been updated;
        no second read is needed.

        This stage is best-effort: errors are logged but never bubble up to the caller.
        """
        if not filtered_results:
            return []

        logger.info("CareerTrendAgent: Stage — KnowledgeBuilder")
        try:
            from job_search_ai.services.knowledge.knowledge_builder import KnowledgeBuilder

            builder = KnowledgeBuilder(
                career_name=student.branch,
                country=student.country,
            )
            result = builder.build(filtered_results)
            logger.info(
                "KnowledgeBuilder: %s  doc=%r  dims=%d  profiles=%d",
                "created" if result.is_new else "updated",
                result.doc_name, result.embedding_dim, len(result.profiles),
            )
            return result.profiles
        except Exception as exc:
            logger.warning(
                "CareerTrendAgent: KnowledgeBuilder failed (%s) — serving raw search evidence",
                exc,
            )
            return []

    def _build_context(self, student: StudentProfile):
        logger.info("CareerTrendAgent: Stage — StudentContextBuilder")
        try:
            context = StudentContextBuilder().build(student)
            logger.info(
                "StudentContextBuilder: readiness=%r  horizon=%r",
                context.placement_readiness, context.recommendation_horizon,
            )
            return context
        except Exception as exc:
            raise CareerTrendAgentError(f"StudentContextBuilder failed: {exc}") from exc

    def _build_prompt(
        self,
        student: StudentProfile,
        evidence: list[Evidence],
        context=None,
        is_kh: bool = True,
    ) -> str:
        logger.info("CareerTrendAgent: Stage — PromptBuilder (%d evidence items)", len(evidence))
        try:
            prompt = PromptBuilder().build(student, evidence, context, is_kh=is_kh)
            logger.info("PromptBuilder: prompt built (%d chars)", len(prompt))
            return prompt
        except Exception as exc:
            raise CareerTrendAgentError(f"PromptBuilder failed: {exc}") from exc

    def _generate_with_service(
        self,
        prompt: str,
        service: LLMService,
    ) -> CareerTrendResponse:
        logger.info("CareerTrendAgent: Stage — LLM generation")
        try:
            response = service.generate(prompt)
            logger.info("LLMService: recommendations generated successfully")
            return response
        except LLMServiceError as exc:
            raise CareerTrendAgentError(f"LLMService failed: {exc}") from exc
        except Exception as exc:
            raise CareerTrendAgentError(f"Unexpected error in LLMService: {exc}") from exc


class CareerTrendAgentError(Exception):
    """
    Raised when the CareerTrendAgent pipeline fails at any stage.
    """
