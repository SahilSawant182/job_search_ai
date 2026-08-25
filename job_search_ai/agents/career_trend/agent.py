"""
CareerTrendAgent — the single public entry point for career trend analysis.

Execution flow (V3)
-------------------

  Student
    │
    ▼  Stage 1 — KnowledgeRetriever  (vector search → MariaDB)
    │             threshold ≥ 0.75
    │
    ├─── Knowledge HIT (≥ min_results careers scored ≥ 0.75)
    │       │
    │       ▼  RecommendationEngine (eligibility gate + scoring)
    │       ▼  PromptBuilder → LLM
    │
    └─── Knowledge MISS or SPARSE
              │
              ▼  QueryBuilder (per-interest queries, up to 2 interests × 2 queries)
              ▼  TavilyService (parallel search)
              ▼  KnowledgeBuilder PER INTEREST
              │     Each interest produces its own LLM extraction call,
              │     yielding up to 3 career profiles per interest.
              │     Profiles are persisted and indexed in Qdrant.
              │
              ▼  Merge all built profiles (deduplicate by career_name)
              ▼  RecommendationEngine (eligibility gate + scoring)
              ▼  PromptBuilder → LLM

Key invariants (unchanged from V2)
-----------------------------------
  - Exactly ONE recommendation LLM call per request.
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
    CareerRecommendation,
    CareerTrendResponse,
    StudentProfile,
)
from job_search_ai.agents.career_trend.student_context_builder import StudentContextBuilder
from job_search_ai.agents.career_trend.tavily_service import TavilyService

logger = logging.getLogger(__name__)

# Maximum number of interests to run separate Tavily+LLM-extraction passes for.
# Benchmark (2026-08-17): =2 gave only +0.5% accuracy vs =1 at +3018ms avg latency cost.
_MAX_MISS_INTERESTS = 1


class CareerTrendAgent:
    """
    Orchestrates the full career trend analysis pipeline (Knowledge-First V3).
    """

    def run(self, student: StudentProfile) -> CareerTrendResponse:
        """
        Execute the Knowledge-First career trend analysis for a student.
        """
        logger.info(
            "CareerTrendAgent starting analysis for student: degree=%r, branch=%r, country=%r",
            student.degree, student.branch, student.country,
        )

        # Normalize student profile shorthands & interests
        from job_search_ai.agents.career_trend.input_normalizer import InputNormalizer
        student = InputNormalizer().normalize(student)

        is_test_student = False
        # Disabled is_test_student override for diagnostic batch test
        
        if is_test_student:
            logger.info("CareerTrendAgent: Test student detected. Returning mock CareerTrendResponse instantly.")
            from datetime import datetime, timezone
            rec = CareerRecommendation(
                career="AI Engineer",
                category="Artificial Intelligence",
                confidence=95,
                why_for_you="Test recommendation.",
                career_stage="Growing",
                future_demand="Very High",
                industry="Technology",
                skills=["Python", "Git", "SQL", "PyTorch", "Machine Learning"]
            )
            response = CareerTrendResponse(
                recommended_paths=[rec],
                strategy="Test strategy for AI Engineer path.",
                generated_at=datetime.now(tz=timezone.utc)
            )
            response.metrics = {
                "total_execution_time": 0.01,
                "parallel_search_time": 0.0,
                "llm_response_time": 0.0,
                "prompt_length": 0,
                "filtered_results_count": 0,
                "model_name": "mock",
                "knowledge_hit": True,
                "avg_similarity_score": 1.0,
                "knowledge_count": 1,
                "tavily_used": False
            }
            return response

        t_total = time.perf_counter()

        # ------------------------------------------------------------------
        # Stage 0 — Settings
        # ------------------------------------------------------------------
        from job_search_ai.services.settings_service import SettingsService
        settings = SettingsService.get()

        # Check Profile Recommendation Knowledge first
        from job_search_ai.agents.career_trend.profile_recommendation_knowledge import ProfileRecommendationKnowledge
        from job_search_ai.agents.career_trend.recommendation_engine import RecommendationEngine
        from job_search_ai.services.knowledge.constants import MIN_FINAL_SCORE
        import frappe
        from datetime import datetime, timezone

        rec_knowledge = ProfileRecommendationKnowledge(settings)
        engine = RecommendationEngine()
        
        hit_payload = rec_knowledge.lookup(student)
        if hit_payload is not None:
            # Reconstruct recommendations by retrieving and re-scoring matching Careers
            career_paths = hit_payload.get("career_paths", [])
            career_names = [cp["career"] for cp in career_paths]
            
            # Fetch retrieved candidates from local MariaDB using these names
            candidates = []
            from job_search_ai.services.knowledge.knowledge_retriever import KnowledgeRetriever
            retriever = KnowledgeRetriever(settings)
            
            class _MetadataHit:
                def __init__(self, doc_id: str):
                    self.id = doc_id
                    self.score = 0.5  # Neutral vector score

            for c_name in career_names:
                docs = frappe.get_all("Career Knowledge", filters={"career_name": c_name, "active": 1}, fields=["name"])
                if docs:
                    try:
                        retrieved_k = retriever._load_from_mariadb([_MetadataHit(docs[0]["name"])], student)
                        if retrieved_k:
                            candidates.extend(retrieved_k)
                    except Exception as exc:
                        logger.warning("Failed to load candidates for %s from DB: %s", c_name, exc)

            scored_careers = engine.rank(student, candidates)
            
            def map_career_stage(stage: str) -> str:
                stage_lower = stage.strip().lower()
                if "immediate" in stage_lower or "established" in stage_lower:
                    return "Established"
                if "growing" in stage_lower:
                    return "Growing"
                if "future" in stage_lower or "emerging" in stage_lower:
                    return "Emerging"
                return "Growing"

            def map_future_demand(demand: str) -> str:
                demand_lower = demand.strip().lower()
                if "very high" in demand_lower:
                    return "Very High"
                if "high" in demand_lower:
                    return "High"
                return "Moderate"

            recommendations: list[CareerRecommendation] = []
            for sc in scored_careers:
                confidence_val = int(sc.final_score * 100)
                if confidence_val >= int(MIN_FINAL_SCORE * 100):
                    cand_skills = list(sc.candidate.skills or [])
                    rec = CareerRecommendation(
                        career=sc.candidate.career_name,
                        category=getattr(sc.candidate, "category", "") or "General",
                        confidence=confidence_val,
                        why_for_you=f"Matched from profile recommendation knowledge. {', '.join(sc.reason_codes[:2])}",
                        career_stage=map_career_stage(getattr(sc.candidate, "career_stage", "")),
                        future_demand=map_future_demand(getattr(sc.candidate, "future_demand", "")),
                        industry=getattr(sc.candidate, "industry", "") or "General",
                        skills=cand_skills,
                    )
                    rec.scores = sc.scores
                    recommendations.append(rec)

            if recommendations:
                # Deterministic strategy description in python — SKIP LLM!
                strategy = (
                    f"Based on a highly similar profile pattern (Combined Similarity: "
                    f"{hit_payload.get('combined_similarity', 0.0) * 100:.1f}%), the following career paths "
                    f"are recommended: {', '.join([r.career for r in recommendations])}. "
                    f"Focus on matching your skills and interests to pursue these fields."
                )
                
                res_obj = CareerTrendResponse(
                    recommended_paths=recommendations,
                    strategy=strategy,
                    generated_at=datetime.now(tz=timezone.utc),
                )
                res_obj.metrics = {
                    "knowledge_hit": True,
                    "knowledge_count": len(recommendations),
                    "avg_similarity_score": hit_payload.get("avg_similarity_score", 0.0),
                    "combined_similarity": hit_payload.get("combined_similarity", 0.0),
                    "tavily_used": False,
                    "knowledge_updated": False,
                    "model_name": "profile_recommendation_knowledge",
                    "llm_response_time": 0.0,
                    "total_execution_time": time.perf_counter() - t_total
                }
                logger.info("CareerTrendAgent: HIT on Profile Recommendation Knowledge (Skip LLM and Tavily)")
                return res_obj

        # ------------------------------------------------------------------
        # Stage 1 — KnowledgeRetriever (Top-K) + Recommendation Scorer Check
        # ------------------------------------------------------------------
        from job_search_ai.agents.career_trend.recommendation_engine import RecommendationEngine
        engine = RecommendationEngine()

        t = time.perf_counter()
        retrieved, avg_similarity = self._retrieve_knowledge_list(student, settings)
        t_retrieval = time.perf_counter() - t

        tavily_used        = False
        knowledge_updated  = False
        filtered_results:  list = []
        queries:           list[str] = []
        raw_results:       list = []
        t_search = t_filter = t_knowledge_build = 0.0

        # Score top-K retrieved candidates using RecommendationEngine
        scored_retrieved = engine.rank(student, retrieved) if retrieved else []
        best_retrieved_score = max((sc.final_score for sc in scored_retrieved), default=0.0)

        # Recommendation-driven knowledge HIT check:
        # A knowledge HIT occurs when local candidates exist and the top candidate clears 0.60 confidence
        if scored_retrieved and best_retrieved_score >= 0.60:
            # ── Knowledge HIT ──────────────────────────────────────────
            logger.info(
                "CareerTrendAgent: Knowledge HIT — %d scored candidates, best_score=%.4f (min=0.60) — skipping Tavily",
                len(scored_retrieved), best_retrieved_score,
            )
            scored_careers = scored_retrieved
            knowledge_hit  = True
        else:
            # ── Knowledge MISS / SPARSE ────────────────────────────────
            knowledge_hit = False
            logger.info(
                "CareerTrendAgent: Knowledge MISS/SPARSE — scored=%d, best_score=%.4f (min=0.60) — running Tavily pipeline",
                len(scored_retrieved), best_retrieved_score,
            )

            # Stage 2 — QueryBuilder (one set of queries covers all interests)
            queries = self._build_queries(student)

            # Stage 3 — Tavily search 
            t = time.perf_counter()   
            try:
                raw_results = self._search(queries)
            except Exception as search_exc:
                logger.warning("CareerTrendAgent: Tavily search failed (%s) — using empty results", search_exc)
                raw_results = []
            t_search    = time.perf_counter() - t
            tavily_used = True

            # Stage 4 — ResultFilter  
            t = time.perf_counter()
            try:
                filtered_results = self._filter(raw_results)
            except Exception as filter_exc:
                logger.warning("CareerTrendAgent: ResultFilter failed (%s) — using empty results", filter_exc)
                filtered_results = []
            t_filter = time.perf_counter() - t

            # Stage 5 — KnowledgeBuilder: one build pass per interest area
            t = time.perf_counter()
            all_built_profiles = self._build_profiles_per_interest(student, filtered_results)
            t_knowledge_build  = time.perf_counter() - t    

            if all_built_profiles:
                knowledge_updated = True
                candidates = all_built_profiles
            else:
                # Fall back to retrieved candidates if available
                candidates = retrieved

            if not candidates:
                logger.error("CareerTrendAgent: no candidates available — returning empty recommendation")
                return self._empty_response(student)

            scored_careers = engine.rank(student, candidates)

        if not scored_careers:
            logger.warning(
                "CareerTrendAgent: all candidates rejected by eligibility gate — returning empty response"
            )
            return self._empty_response(student)

        def map_career_stage(stage: str) -> str:
            stage_lower = stage.strip().lower()
            if "immediate" in stage_lower or "established" in stage_lower:
                return "Established"
            if "growing" in stage_lower:
                return "Growing"
            if "future" in stage_lower or "emerging" in stage_lower:
                return "Emerging"
            return "Growing"

        def map_future_demand(demand: str) -> str:
            demand_lower = demand.strip().lower()
            if "very high" in demand_lower:
                return "Very High"
            if "high" in demand_lower:
                return "High"
            return "Moderate"

        recommendations: list[CareerRecommendation] = []
        for sc in scored_careers[:20]:
            confidence_val = int(sc.final_score * 100)
            if confidence_val < int(MIN_FINAL_SCORE * 100):  # Require >= MIN_FINAL_SCORE Match Confidence
                continue
            cand_skills = list(sc.candidate.skills or [])
            rec = CareerRecommendation(
                career=sc.candidate.career_name,
                category=getattr(sc.candidate, "category", "") or "General",
                confidence=confidence_val,
                why_for_you="",
                career_stage=map_career_stage(getattr(sc.candidate, "career_stage", "")),
                future_demand=map_future_demand(getattr(sc.candidate, "future_demand", "")),
                industry=getattr(sc.candidate, "industry", "") or "General",
                skills=cand_skills,
            )
            rec.scores = sc.scores
            recommendations.append(rec)

        if not recommendations:
            logger.warning(
                "CareerTrendAgent: no candidates cleared the >= %d%% confidence threshold — returning empty response",
                int(MIN_FINAL_SCORE * 100)
            )
            return self._empty_response(student)

        # Top 5 python-ranked candidates feed the LLM prompt
        top_candidates = [
            sc.candidate 
            for sc in scored_careers 
            if int(sc.final_score * 100) >= int(MIN_FINAL_SCORE * 100)
        ][:5]
        evidence = Evidence.from_knowledge(top_candidates)

        # ------------------------------------------------------------------
        # Stage 6 — StudentContext
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
        response = self._generate_with_service(prompt, llm_service, recommendations)
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
            "  PERFORMANCE METRICS (Knowledge-First V3)\n"
            "============================================================\n"
            "Knowledge Hit          : %s\n"
            "Knowledge Count        : %d\n"
            "Avg Similarity Score   : %.4f\n"
            "Tavily Used            : %s\n"
            "Knowledge Updated      : %s\n"
            "Candidates After Gate  : %d\n"
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
            len(scored_careers),
            t_retrieval,
            t_search,
            t_filter,
            t_knowledge_build,
            t_context,
            t_prompt,
            t_llm,
            prompt_len,
            est_tokens,
            llm_service.model_name,
            total_time,
        )

        response.metrics = {
            "knowledge_hit":          knowledge_hit,
            "knowledge_count":        len(retrieved),
            "avg_similarity_score":   avg_similarity,
            "tavily_used":            tavily_used,
            "knowledge_updated":      knowledge_updated,
            "query_count":            len(queries) if not knowledge_hit else 0,
            "parallel_search_time":   t_search if tavily_used else 0.0,
            "kb_build_time":          t_knowledge_build if tavily_used else 0.0,
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
            "CareerTrendAgent finished — %d recommendations  hit=%s  tavily=%s",
            len(response.recommended_paths), knowledge_hit, tavily_used,
        )

        try:
            rec_knowledge.store(student, response)
        except Exception as exc:
            logger.warning("Failed to store response in ProfileRecommendationKnowledge: %s", exc)

        return response

    # ------------------------------------------------------------------
    # Stage runners
    # ------------------------------------------------------------------

    def _retrieve_knowledge_list(
        self,
        student: StudentProfile,
        settings,
    ) -> tuple[list, float]:
        """Run KnowledgeRetriever to load candidate careers from cache."""
        try:
            from job_search_ai.services.knowledge.knowledge_retriever import KnowledgeRetriever
            retriever = KnowledgeRetriever(settings=settings)
            retrieved = retriever.retrieve(student)
        except Exception as exc:
            logger.warning(
                "CareerTrendAgent: KnowledgeRetriever failed (%s) — falling back to Tavily", exc
            )
            return [], 0.0

        if not retrieved:
            return [], 0.0

        avg_similarity = sum(r.similarity for r in retrieved) / len(retrieved)
        return retrieved, avg_similarity

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

    def _build_profiles_per_interest(
        self,
        student: StudentProfile,
        filtered_results: list,
    ) -> list:
        """
        Run KnowledgeBuilder once per interest area (up to _MAX_MISS_INTERESTS).

        Each pass calls CareerLLMExtractor with the specific interest as the
        career_focus hint, so the LLM knows which domain to extract careers for.
        All resulting profiles are merged and returned as a flat list.
        """
        # Determine which interests to target
        interests_to_build = (
            student.interests[:_MAX_MISS_INTERESTS]
            if student.interests
            else [self._infer_career_focus(student)]
        )

        all_profiles: list = []
        seen_careers: set[str] = set()

        for interest in interests_to_build:
            logger.info(
                "CareerTrendAgent: Stage — KnowledgeBuilder for interest=%r", interest
            )
            try:
                from job_search_ai.services.knowledge.knowledge_builder import KnowledgeBuilder
                builder = KnowledgeBuilder(
                    career_name=interest,
                    country=student.country,
                    student=student,
                )
                result = builder.build(filtered_results)
                logger.info(
                    "KnowledgeBuilder[%r]: %s  doc=%r  dims=%d  profiles=%d",
                    interest,
                    "created" if result.is_new else "updated",
                    result.doc_name, result.embedding_dim, len(result.profiles),
                )
                for profile in result.profiles:
                    key = profile.career_name.lower().strip()
                    if key not in seen_careers:
                        seen_careers.add(key)
                        all_profiles.append(profile)
            except Exception as exc:
                logger.warning(
                    "CareerTrendAgent: KnowledgeBuilder failed for interest=%r (%s) — skipping",
                    interest, exc,
                )

        logger.info(
            "CareerTrendAgent: _build_profiles_per_interest complete — %d unique profiles",
            len(all_profiles),
        )
        return all_profiles

    def _infer_career_focus(self, student: StudentProfile) -> str:
        """Derive the most relevant career focus (interests → skills → branch)."""
        if student.interests:
            return student.interests[0]
        if student.skills:
            return student.skills[0]
        return student.branch

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
            prompt = PromptBuilder().build(evidence, context, is_kh=is_kh)
            logger.info("PromptBuilder: prompt built (%d chars)", len(prompt))
            return prompt
        except Exception as exc:
            raise CareerTrendAgentError(f"PromptBuilder failed: {exc}") from exc

    def _generate_with_service(
        self,
        prompt: str,
        service: LLMService,
        recommendations: list[CareerRecommendation],
    ) -> CareerTrendResponse:
        logger.info("CareerTrendAgent: Stage — LLM generation")
        try:
            response = service.generate(prompt, recommendations)
            logger.info("LLMService: recommendations generated successfully")
            return response
        except LLMServiceError as exc:
            raise CareerTrendAgentError(f"LLMService failed: {exc}") from exc
        except Exception as exc:
            raise CareerTrendAgentError(f"Unexpected error in LLMService: {exc}") from exc

    def _empty_response(self, student: StudentProfile) -> "CareerTrendResponse":
        """Return a graceful empty response when no suitable careers are found."""
        from datetime import datetime, timezone
        from job_search_ai.agents.career_trend.schemas import CareerTrendResponse
        response = CareerTrendResponse(
            recommended_paths=[],
            strategy=(
                f"We could not find suitable career matches for your profile "
                f"({student.degree} in {student.branch}, Year {student.year}). "
                "Please try again with more specific interests or skills."
            ),
            generated_at=datetime.now(tz=timezone.utc),
        )
        response.metrics = {
            "knowledge_hit": False,
            "knowledge_count": 0,
            "avg_similarity_score": 0.0,
            "tavily_used": True,
            "knowledge_updated": False,
        }
        return response


class CareerTrendAgentError(Exception):
    """
    Raised when the CareerTrendAgent pipeline fails at any stage.
    """
