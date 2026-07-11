"""
CareerTrendAgent — the single public entry point for career trend analysis.

Responsibility:
    Orchestrate the full pipeline from a StudentProfile to a
    CareerTrendResponse. Measure and log execution metrics for each stage.
"""

from __future__ import annotations

import logging
import time

from job_search_ai.agents.career_trend.llm_service import LLMService, LLMServiceError
from job_search_ai.agents.career_trend.prompt_builder import PromptBuilder
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
    """

    def run(self, student: StudentProfile) -> CareerTrendResponse:
        """
        Execute the complete career trend analysis for a student and trace metrics.
        """
        logger.info(
            "CareerTrendAgent starting analysis for student: branch=%r, country=%r.",
            student.branch,
            student.country,
        )

        start_total = time.perf_counter()

        # Stage 1: Build search queries
        start_t = time.perf_counter()
        queries = self._build_queries(student)
        t_query_builder = time.perf_counter() - start_t

        # Stage 2: Fetch search results (Parallel Search)
        start_t = time.perf_counter()
        raw_results = self._search(queries)
        t_parallel_search = time.perf_counter() - start_t

        # Stage 3: Clean and deduplicate results
        start_t = time.perf_counter()
        filtered_results = self._filter(raw_results)
        t_filtering = time.perf_counter() - start_t

        # Stage 3.5: Deterministic student context builder (no LLM, no network)
        start_t = time.perf_counter()
        context = self._build_context(student)
        t_context_builder = time.perf_counter() - start_t

        # Stage 4: Build the LLM prompt
        start_t = time.perf_counter()
        prompt = self._build_prompt(student, filtered_results, context)
        t_prompt_builder = time.perf_counter() - start_t

        # Stage 5: Generate career recommendations
        start_t = time.perf_counter()
        llm_service = LLMService()
        response = self._generate_with_service(prompt, llm_service)
        t_llm = time.perf_counter() - start_t

        total_time = time.perf_counter() - start_total

        # Compute metrics
        prompt_len = len(prompt)
        est_tokens = prompt_len // 4

        # Log metrics block
        logger.info(
            "\n"
            "============================================================\n"
            "  PERFORMANCE METRICS\n"
            "============================================================\n"
            "Query Count          : %d\n"
            "Parallel Search Time : %.3f sec\n"
            "Raw Results Count    : %d\n"
            "Filtered Results     : %d\n"
            "Readiness Stage      : %s\n"
            "Horizon              : %s\n"
            "Prompt Length        : %d chars\n"
            "Estimated Tokens     : %d\n"
            "Model Name           : %s\n"
            "LLM Response Time    : %.3f sec\n"
            "Total Execution Time : %.3f sec\n"
            "============================================================\n"
            "Stage 1 (Queries)    : %.3f sec\n"
            "Stage 3 (Filter)     : %.3f sec\n"
            "Stage 3.5 (Context)  : %.3f sec\n"
            "Stage 4 (Prompt)     : %.3f sec\n"
            "============================================================",
            len(queries),
            t_parallel_search,
            len(raw_results),
            len(filtered_results),
            context.placement_readiness,
            context.recommendation_horizon,
            prompt_len,
            est_tokens,
            llm_service.model_name,
            t_llm,
            total_time,
            t_query_builder,
            t_filtering,
            t_context_builder,
            t_prompt_builder,
        )

        # Attach metrics dynamically to the response
        response.metrics = {
            "query_count": len(queries),
            "parallel_search_time": t_parallel_search,
            "raw_results_count": len(raw_results),
            "filtered_results_count": len(filtered_results),
            "placement_readiness": context.placement_readiness,
            "recommendation_horizon": context.recommendation_horizon,
            "prompt_length": prompt_len,
            "estimated_tokens": est_tokens,
            "model_name": llm_service.model_name,
            "llm_response_time": t_llm,
            "total_execution_time": total_time,
        }

        logger.info(
            "CareerTrendAgent finished. Returning %d career recommendations.",
            len(response.recommended_paths),
        )
        return response

    # ------------------------------------------------------------------
    # Private stage runners
    # ------------------------------------------------------------------

    def _build_queries(self, student: StudentProfile) -> list[str]:
        logger.info("Stage 1/5 — Building search queries.")
        try:
            queries = QueryBuilder().build(student)
            logger.info("Stage 1/5 — %d queries built.", len(queries))
            return queries
        except Exception as exc:
            raise CareerTrendAgentError(
                f"QueryBuilder failed: {exc}"
            ) from exc

    def _search(self, queries: list[str]) -> list:
        logger.info("Stage 2/5 — Searching the web in parallel.")
        try:
            results = TavilyService().search(queries)
            logger.info("Stage 2/5 — %d raw results retrieved.", len(results))
            return results
        except Exception as exc:
            raise CareerTrendAgentError(
                f"TavilyService failed: {exc}"
            ) from exc

    def _filter(self, raw_results: list) -> list:
        logger.info("Stage 3/6 — Filtering and deduplicating results.")
        try:
            filtered = ResultFilter().filter(raw_results)
            logger.info("Stage 3/6 — %d results after filtering.", len(filtered))
            return filtered
        except Exception as exc:
            raise CareerTrendAgentError(
                f"ResultFilter failed: {exc}"
            ) from exc

    def _build_context(self, student: StudentProfile):
        logger.info("Stage 3.5/6 — Running deterministic StudentContextBuilder.")
        try:
            context = StudentContextBuilder().build(student)
            logger.info(
                "Stage 3.5/6 — Readiness: %r, Horizon: %r.",
                context.placement_readiness,
                context.recommendation_horizon,
            )
            return context
        except Exception as exc:
            raise CareerTrendAgentError(
                f"StudentContextBuilder failed: {exc}"
            ) from exc

    def _build_prompt(self, student: StudentProfile, results: list, context=None) -> str:
        logger.info("Stage 4/6 — Building LLM prompt.")
        try:
            prompt = PromptBuilder().build(student, results, context)
            logger.info("Stage 4/6 — Prompt built (%d chars).", len(prompt))
            return prompt
        except Exception as exc:
            raise CareerTrendAgentError(
                f"PromptBuilder failed: {exc}"
            ) from exc

    def _generate_with_service(self, prompt: str, service: LLMService) -> CareerTrendResponse:
        logger.info("Stage 5/6 — Generating career recommendations via LLM.")
        try:
            response = service.generate(prompt)
            logger.info("Stage 5/6 — Recommendations generated successfully.")
            return response
        except LLMServiceError as exc:
            raise CareerTrendAgentError(
                f"LLMService failed: {exc}"
            ) from exc
        except Exception as exc:
            raise CareerTrendAgentError(
                f"Unexpected error in LLMService: {exc}"
            ) from exc


class CareerTrendAgentError(Exception):
    """
    Raised when the CareerTrendAgent pipeline fails at any stage.
    """
