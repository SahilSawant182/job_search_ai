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

            if not recommendations and career_paths:
                for cp in career_paths:
                    hist_score = cp.get("historical_score", 0.8)
                    conf = int(hist_score * 100) if hist_score <= 1.0 else int(hist_score)
                    rec = CareerRecommendation(
                        career=cp.get("career", ""),
                        category=hit_payload.get("academic_domain", "General").title(),
                        confidence=conf,
                        why_for_you=f"Recommended for {student.degree} ({student.branch}) student based on cached profile match.",
                        career_stage="Growing",
                        future_demand="High",
                        industry=hit_payload.get("academic_domain", "General").title(),
                        skills=hit_payload.get("skills", []),
                    )
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
                try:
                    self._async_ensure_career_doctypes_persisted(student, res_obj)
                except Exception as p_exc:
                    logger.warning("Stage 0: could not persist career doctypes: %s", p_exc)

                logger.info("CareerTrendAgent: HIT on Profile Recommendation Knowledge (Skip LLM and Tavily)")
                return _sanitize_response_recommendations(student, res_obj)

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

        # Fallback check across all MariaDB active Career Knowledge docs if vector search yielded no strong hit
        if not scored_retrieved or best_retrieved_score < 0.35:
            try:
                import frappe
                all_db_docs = frappe.get_all("Career Knowledge", filters={"active": 1}, fields=["name"])
                if all_db_docs:
                    from job_search_ai.services.knowledge.knowledge_retriever import KnowledgeRetriever
                    retriever = KnowledgeRetriever(settings)
                    class _StubHit:
                        def __init__(self, doc_id: str):
                            self.id = doc_id
                            self.score = 0.5
                    all_candidates = retriever._load_from_mariadb([_StubHit(d["name"]) for d in all_db_docs], student)
                    scored_all = engine.rank(student, all_candidates)
                    if scored_all:
                        best_all_score = scored_all[0].final_score
                        if best_all_score >= 0.30:
                            scored_retrieved = scored_all
                            best_retrieved_score = best_all_score
            except Exception as db_fallback_exc:
                logger.warning("MariaDB candidate fallback failed: %s", db_fallback_exc)

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

        # Recommendation-driven fast execution check:
        # A knowledge HIT occurs when local candidates exist and clear match threshold (>= 0.30)
        if scored_retrieved and best_retrieved_score >= 0.30:
            logger.info(
                "CareerTrendAgent: Knowledge HIT — %d scored candidates, best_score=%.4f (min=0.30) — fast Python response",
                len(scored_retrieved), best_retrieved_score,
            )
            recommendations: list[CareerRecommendation] = []
            for sc in scored_retrieved[:5]:
                confidence_val = int(sc.final_score * 100)
                if confidence_val < int(MIN_FINAL_SCORE * 100):
                    continue
                cand_skills = list(sc.candidate.skills or [])
                reasons = ", ".join(sc.reason_codes[:2]) if sc.reason_codes else "Strong alignment with academic background and skills"
                rec = CareerRecommendation(
                    career=sc.candidate.career_name,
                    category=getattr(sc.candidate, "category", "") or "General",
                    confidence=confidence_val,
                    why_for_you=f"Recommended for {student.degree} ({student.branch}) student. {reasons}.",
                    career_stage=map_career_stage(getattr(sc.candidate, "career_stage", "")),
                    future_demand=map_future_demand(getattr(sc.candidate, "future_demand", "")),
                    industry=getattr(sc.candidate, "industry", "") or "General",
                    skills=cand_skills,
                )
                rec.scores = sc.scores
                recommendations.append(rec)

            if recommendations:
                top_names = [r.career for r in recommendations[:3]]
                strategy = (
                    f"Based on your degree ({student.degree} in {student.branch}, Year {student.year}) and skills "
                    f"({', '.join(student.skills[:3]) if student.skills else 'your background'}), "
                    f"the top recommended career paths are: {', '.join(top_names)}. "
                    f"Focus on building core skills in these areas to optimize placement opportunities."
                )
                res_obj = CareerTrendResponse(
                    recommended_paths=recommendations,
                    strategy=strategy,
                    generated_at=datetime.now(tz=timezone.utc),
                )
                res_obj.metrics = {
                    "knowledge_hit": True,
                    "knowledge_count": len(recommendations),
                    "avg_similarity_score": avg_similarity,
                    "tavily_used": False,
                    "knowledge_updated": False,
                    "model_name": "local_career_knowledge",
                    "llm_response_time": 0.0,
                    "total_execution_time": time.perf_counter() - t_total,
                }
                # Store in ProfileRecommendationKnowledge and ensure DocTypes exist
                try:
                    rec_knowledge.store(student, res_obj)
                    self._async_ensure_career_doctypes_persisted(student, res_obj)
                except Exception as st_exc:
                    logger.warning("Failed to store profile recommendation: %s", st_exc)

                logger.info("CareerTrendAgent: Returned fast Python response in %.3fs", time.perf_counter() - t_total)
                return _sanitize_response_recommendations(student, res_obj)

        # ── Knowledge MISS / SPARSE ────────────────────────────────
        logger.info(
            "CareerTrendAgent: Knowledge MISS — scored=%d, best_score=%.4f — calling single-pass direct LLM generator",
            len(scored_retrieved), best_retrieved_score,
        )
        res_direct = self._generate_from_profile_direct(student, t_total, tavily_used=False)
        return _sanitize_response_recommendations(student, res_direct)


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

    def _generate_from_profile_direct(
        self,
        student: StudentProfile,
        t_total: float,
        tavily_used: bool = True,
    ) -> "CareerTrendResponse":
        """
        Last-mile fallback — fires when no knowledge candidates are available.
        Uses SmartCareerMapper first (domain-aware python matcher).
        If that fails (truly novel profile), it falls back to the LLM.
        """
        from datetime import datetime, timezone
        from job_search_ai.agents.career_trend.smart_career_mapper import SmartCareerMapper
        
        logger.info("CareerTrendAgent: _generate_from_profile_direct — attempting SmartCareerMapper")
        
        # 1. Try SmartCareerMapper first (instant, domain-aware)
        mapper = SmartCareerMapper()
        mapped_recs = mapper.map_career(student, top_k=3)
        
        if mapped_recs:
            logger.info("CareerTrendAgent: SmartCareerMapper returned %d paths instantly.", len(mapped_recs))
            
            top_names = [r.career for r in mapped_recs[:3]]
            strategy = (
                f"Based on your degree ({student.degree} in {student.branch}, Year {student.year}) and skills "
                f"({', '.join(student.skills[:3]) if student.skills else 'your background'}), "
                f"the top recommended career paths are: {', '.join(top_names)}. "
                f"Focus on building core skills in these areas to optimize placement opportunities."
            )
            
            response = CareerTrendResponse(
                recommended_paths=mapped_recs,
                strategy=strategy,
                generated_at=datetime.now(tz=timezone.utc),
            )
            
            response.metrics = {
                "knowledge_hit":          False,
                "knowledge_count":        len(mapped_recs),
                "avg_similarity_score":   0.0,
                "tavily_used":            False,
                "knowledge_updated":      False,
                "model_name":             "smart_career_mapper",
                "llm_response_time":      0.0,
                "total_execution_time":   time.perf_counter() - t_total,
                "direct_profile_prompt":  False,
            }
        else:
            # 2. Fall back to LLM ONLY if SmartCareerMapper failed (novel niche profile)
            logger.info("CareerTrendAgent: SmartCareerMapper yielded. Calling LLM with profile-only prompt")
            try:
                context = StudentContextBuilder().build(student)
            except Exception as ctx_exc:
                logger.warning("CareerTrendAgent: StudentContextBuilder failed in direct path (%s)", ctx_exc)
                return self._fallback_deterministic_response(student, t_total)

            try:
                prompt = PromptBuilder().build_direct(context)
            except Exception as pb_exc:
                logger.warning("CareerTrendAgent: PromptBuilder.build_direct failed (%s)", pb_exc)
                return self._fallback_deterministic_response(student, t_total)

            t_llm_start = time.perf_counter()
            try:
                llm_service = LLMService()
                response = llm_service.generate_direct(prompt)
                t_llm = time.perf_counter() - t_llm_start
            except Exception as llm_exc:
                logger.error(
                    "CareerTrendAgent: generate_direct LLM call failed (%s) — falling back to deterministic response",
                    llm_exc,
                )
                return self._fallback_deterministic_response(student, t_total)

            response.metrics = {
                "knowledge_hit":          False,
                "knowledge_count":        0,
                "avg_similarity_score":   0.0,
                "tavily_used":            tavily_used,
                "knowledge_updated":      False,
                "model_name":             getattr(LLMService(), "model_name", "unknown"),
                "llm_response_time":      t_llm,
                "total_execution_time":   time.perf_counter() - t_total,
                "direct_profile_prompt":  True,
            }

        logger.info(
            "CareerTrendAgent: _generate_from_profile_direct complete — %d recommendations",
            len(response.recommended_paths),
        )

        # Persist so the same profile benefits from cache on the next request
        try:
            from job_search_ai.agents.career_trend.profile_recommendation_knowledge import ProfileRecommendationKnowledge
            from job_search_ai.services.settings_service import SettingsService
            settings = SettingsService.get()
            ProfileRecommendationKnowledge(settings).store(student, response)
            self._async_ensure_career_doctypes_persisted(student, response)
        except Exception as store_exc:
            logger.warning("CareerTrendAgent: could not store direct response: %s", store_exc)

        return response

    def _fallback_deterministic_response(self, student: StudentProfile, t_total: float) -> "CareerTrendResponse":
        """
        Fallback deterministic generator when LLM calls fail or time out.
        Ensures the user ALWAYS receives career recommendations within latency targets.
        """
        from datetime import datetime, timezone
        from job_search_ai.agents.career_trend.schemas import CareerTrendResponse, CareerRecommendation

        branch_clean = (student.branch or "Technology").strip()
        primary_interest = student.interests[0] if student.interests else branch_clean
        primary_skill = student.skills[0] if student.skills else "Domain Analysis"

        career1_name = f"{primary_interest} Specialist" if primary_interest.lower() not in branch_clean.lower() else f"{branch_clean} Specialist"
        career2_name = f"{branch_clean} Analyst"

        recs = [
            CareerRecommendation(
                career=career1_name,
                category=branch_clean,
                confidence=75,
                why_for_you=f"Recommended for {student.degree} ({branch_clean}) student based on interest in {primary_interest}.",
                career_stage="Growing",
                future_demand="High",
                industry=branch_clean,
                skills=student.skills[:4] if len(student.skills) >= 2 else [primary_skill, "Problem Solving", "Domain Analysis", "Project Management"],
            ),
            CareerRecommendation(
                career=career2_name,
                category=branch_clean,
                confidence=70,
                why_for_you=f"Strong career path for {branch_clean} students focusing on analytical and domain skills.",
                career_stage="Growing",
                future_demand="High",
                industry=branch_clean,
                skills=student.skills[:3] + ["Data Analysis", "Communication"] if student.skills else ["Analytical Thinking", "Data Analysis", "Domain Knowledge"],
            ),
        ]

        res = CareerTrendResponse(
            recommended_paths=recs,
            strategy=f"Based on your degree ({student.degree} in {branch_clean}), focus on building core skills in {primary_interest} and {primary_skill} to optimize career growth.",
            generated_at=datetime.now(tz=timezone.utc),
        )
        res.metrics = {
            "knowledge_hit": False,
            "knowledge_count": len(recs),
            "avg_similarity_score": 0.0,
            "tavily_used": False,
            "knowledge_updated": False,
            "model_name": "fallback_generator",
            "llm_response_time": 0.0,
            "total_execution_time": time.perf_counter() - t_total,
        }
        try:
            self._async_ensure_career_doctypes_persisted(student, res)
        except Exception as exc:
            logger.warning("Could not persist fallback career doctypes: %s", exc)
        return res

    def _empty_response(self, student: StudentProfile) -> "CareerTrendResponse":
        """Fallback empty or deterministic response when LLM or context fails."""
        return self._fallback_deterministic_response(student, time.perf_counter())

    def _async_ensure_career_doctypes_persisted(self, student: StudentProfile, response: "CareerTrendResponse") -> None:
        """Run persistence in a background thread to prevent blocking API responses."""
        import threading
        import frappe
        # We must clone/dictify the response or run it safely
        site_name = getattr(frappe.local, 'site', 'job_search_ai')
        t = threading.Thread(target=_ensure_career_doctypes_persisted, args=(site_name, student, response), daemon=True)
        t.start()


def _sanitize_response_recommendations(student: StudentProfile, response: CareerTrendResponse) -> CareerTrendResponse:
    """
    Guarantees:
    1. Minimum 2 recommendations for career path (never empty, never 1 item).
    2. Every recommendation contains a complete list of required skills.
    3. Auto-populates missing skills from MariaDB or student domain context.
    """
    if not response:
        return response

    import frappe
    from job_search_ai.agents.career_trend.schemas import CareerRecommendation

    def fetch_db_skills(career_name: str) -> list[str]:
        if not career_name:
            return []
        try:
            ck_name = frappe.db.get_value("Career Knowledge", {"career_name": career_name}, "name")
            if ck_name:
                doc = frappe.get_doc("Career Knowledge", ck_name)
                skills = [row.skill_name for row in (doc.skills or []) if row.skill_name]
                if skills:
                    return skills
            cp_name = frappe.db.get_value("Career Path", {"target_role": career_name}, "name") or career_name
            if frappe.db.exists("Career Path", cp_name):
                cp_doc = frappe.get_doc("Career Path", cp_name)
                prereqs = [row.prerequisite_skills for row in (cp_doc.prerequisite_skills or []) if row.prerequisite_skills]
                m_skills = [row.skill for row in (cp_doc.path_milestone or []) if row.skill]
                all_s = list(dict.fromkeys(prereqs + m_skills))
                if all_s:
                    return all_s
        except Exception:
            pass
        return []

    branch_clean = (student.branch or "Technology").strip()
    primary_interest = student.interests[0] if student.interests else branch_clean
    primary_skill = student.skills[0] if student.skills else "Domain Analysis"

    paths = list(response.recommended_paths or [])

    # Step 1: Ensure every existing recommendation has required skills
    for rec in paths:
        if not rec.skills or len(rec.skills) < 3:
            db_skills = fetch_db_skills(rec.career)
            if db_skills and len(db_skills) >= 3:
                rec.skills = db_skills
            else:
                base_skills = list(rec.skills or [])
                for s in (student.skills or []):
                    if s and s not in base_skills:
                        base_skills.append(s)
                default_domain_skills = [
                    "Problem Solving", "Domain Analysis", "Data Analysis",
                    "Project Management", "Technical Communication", "Core Domain Concepts"
                ]
                for ds in default_domain_skills:
                    if len(base_skills) >= 5:
                        break
                    if ds not in base_skills:
                        base_skills.append(ds)
                rec.skills = base_skills

    # Step 2: Ensure minimum 2 recommendations
    if len(paths) == 0:
        rec1 = CareerRecommendation(
            career=f"{primary_interest} Specialist" if primary_interest.lower() not in branch_clean.lower() else f"{branch_clean} Specialist",
            category=branch_clean,
            confidence=75,
            why_for_you=f"Recommended for {student.degree} ({branch_clean}) student based on interest in {primary_interest}.",
            career_stage="Growing",
            future_demand="High",
            industry=branch_clean,
            skills=student.skills[:4] if len(student.skills) >= 2 else [primary_skill, "Problem Solving", "Domain Analysis", "Project Management"],
        )
        rec2 = CareerRecommendation(
            career=f"{branch_clean} Analyst",
            category=branch_clean,
            confidence=70,
            why_for_you=f"Strong career path for {branch_clean} students focusing on analytical and domain skills.",
            career_stage="Growing",
            future_demand="High",
            industry=branch_clean,
            skills=student.skills[:3] + ["Data Analysis", "Communication"] if student.skills else ["Analytical Thinking", "Data Analysis", "Domain Knowledge"],
        )
        paths = [rec1, rec2]

    elif len(paths) == 1:
        existing_name = paths[0].career
        fallback_name = f"{branch_clean} Specialist" if "Analyst" in existing_name else f"{branch_clean} Analyst"
        if fallback_name == existing_name:
            fallback_name = f"{primary_interest} Consultant"
        rec2 = CareerRecommendation(
            career=fallback_name,
            category=branch_clean,
            confidence=70,
            why_for_you=f"Complementary career path for {student.degree} ({branch_clean}) student.",
            career_stage="Growing",
            future_demand="High",
            industry=branch_clean,
            skills=student.skills[:4] if len(student.skills) >= 2 else [primary_skill, "Data Analysis", "Problem Solving", "Domain Knowledge"],
        )
        paths.append(rec2)

    response.recommended_paths = paths
    try:
        import threading
        import frappe
        site_name = getattr(frappe.local, 'site', 'job_search_ai')
        t = threading.Thread(target=_ensure_career_doctypes_persisted, args=(site_name, student, response), daemon=True)
        t.start()
    except Exception as exc:
        logger.warning("Could not persist career doctypes during sanitize: %s", exc)
    return response


def _ensure_career_doctypes_persisted(site_name: str, student: StudentProfile, response: CareerTrendResponse) -> None:
    """
    Ensure all generated career recommendations exist as 'Career Knowledge' and 'Career Path'
    DocTypes in MariaDB so that Skill Gap Analysis and Student Path Enrollment (Activate Path)
    succeed immediately in < 1 second.
    """
    if not response or not response.recommended_paths:
        return

    import frappe
    frappe.init(site=site_name)
    frappe.connect()
    
    try:
        def ensure_skill(s_name: str):
            s_clean = s_name.strip()
            if s_clean and not frappe.db.exists("Skill", s_clean):
                try:
                    frappe.get_doc({
                        "doctype": "Skill",
                        "skill_name": s_clean,
                        "skill_category": "Technical",
                        "skill_level_schema": "Beginner→Expert"
                    }).insert(ignore_permissions=True)
                except Exception:
                    pass

        for rec in response.recommended_paths:
            career_name = (rec.career or "").strip()
            if not career_name:
                continue

            skills = rec.skills or student.skills or ["Domain Knowledge", "Problem Solving"]
            for s in skills:
                ensure_skill(s)

            # 1. Ensure Career Knowledge doc exists
            if not frappe.db.exists("Career Knowledge", {"career_name": career_name}):
                try:
                    ck_doc = frappe.get_doc({
                        "doctype": "Career Knowledge",
                        "career_name": career_name,
                        "industry": getattr(rec, "industry", None) or getattr(rec, "category", None) or student.branch or "General",
                        "active": 1,
                        "skills": [{"skill_name": s, "skill_type": "Required"} for s in skills]
                    })
                    ck_doc.insert(ignore_permissions=True)
                    logger.info("Auto-created Career Knowledge doc for '%s'", career_name)
                except Exception as exc:
                    logger.warning("Could not auto-create Career Knowledge for '%s': %s", career_name, exc)

        try:
            frappe.db.commit()
        except Exception as exc:
            logger.error("Thread DB commit error: %s", exc)
    finally:
        frappe.destroy()


class CareerTrendAgentError(Exception):
    """
    Raised when the CareerTrendAgent pipeline fails at any stage.
    """
