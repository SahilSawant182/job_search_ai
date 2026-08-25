"""
Skill Gap Service Module.

Orchestrates data retrieval from Frappe DB (Student Skill, Job Description)
and delegates comparison logic to the pure Python SkillGapAnalyzer engine.
"""

from __future__ import annotations

import logging
import time
from typing import List, Optional, Tuple

import frappe
from job_search_ai.services.skill_gap.analyzer import SkillGapAnalyzer
from job_search_ai.services.skill_gap.matcher import SemanticSkillMatcher
from job_search_ai.services.skill_gap.skill_embedding_index import SkillEmbeddingResolver
from job_search_ai.services.skill_gap.normalizer import (
    normalize_skill,
    parse_skill_string,
)
from job_search_ai.services.skill_gap.schemas import (
    SkillGapReport,
    StudentSkillItem,
)

logger = logging.getLogger(__name__)


class SkillGapService:
    """
    Frappe Service Layer for Skill Gap Analysis.
    Fetches data from DB and calls pure SkillGapAnalyzer.
    """

    def __init__(
        self,
        analyzer: Optional[SkillGapAnalyzer] = None,
        matcher: Optional[SemanticSkillMatcher] = None,
    ) -> None:
        self.analyzer = analyzer or SkillGapAnalyzer()
        self.matcher = matcher or SemanticSkillMatcher(
            skill_resolver=self._build_skill_resolver()
        )


    def _build_skill_resolver(self) -> Optional[SkillEmbeddingResolver]:
        try:
            return SkillEmbeddingResolver()
        except Exception as exc:
            logger.warning(
                "SkillGapService: persistent skill resolver unavailable; semantic index disabled: %s",
                exc,
            )
            return None

    @staticmethod
    def get_configured_readiness_threshold(override: Optional[float] = None) -> float:
        """
        Get readiness threshold percentage.
        Prioritizes explicit override -> Job Search AI Settings -> default 70.0%.
        """
        if override is not None and float(override) > 0:
            return float(override)
        try:
            if hasattr(frappe, "db") and frappe.db.exists("DocType", "Job Search AI Settings"):
                val = frappe.db.get_single_value("Job Search AI Settings", "skill_readiness_threshold")
                if val is not None and float(val) > 0:
                    return float(val)
        except Exception:
            pass
        return 70.0

    def get_skill_gap_report(
        self,
        student: str,
        career: Optional[str | SkillProfile | dict] = None,
        readiness_threshold: Optional[float] = None,
        role: Optional[str] = None,
        job_description: Optional[str] = None,
    ) -> SkillGapReport:
        """
        Fetch data from Skill Knowledge/SkillAgent and generate structured Skill Gap Report.

        Args:
            student: Student email or Student DocName.
            career: Target career title, SkillProfile object, or dictionary.
            readiness_threshold: Benchmark threshold for job readiness.
            role: Deprecated, backward compatible alias for career.
            job_description: Deprecated, backward compatible alias for career.

        Returns:
            SkillGapReport structured output.
        """
        start_time = time.perf_counter()
        effective_threshold = self.get_configured_readiness_threshold(readiness_threshold)

        # Validate student existence
        if student and student != "Generic":
            resolved_student = self._resolve_student_docname(student)
            if not frappe.db.exists("Student", resolved_student):
                frappe.throw(f"Student '{student}' not found.", frappe.DoesNotExistError)
            # 1. Fetch verified student skills (ai_verified = 1)
            student_skills = self.fetch_verified_student_skills(resolved_student)
        else:
            resolved_student = "Generic"
            student_skills = []

        # Force reload caching layers to ensure database updates are instantly picked up
        from job_search_ai.services.skill_gap.normalizer import initialize_normalization_cache
        from job_search_ai.services.skill_gap.relationship import initialize_relationship_cache
        initialize_normalization_cache(force=True)
        initialize_relationship_cache(force=True)

        # 2. Resolve skill profile from Skill Agent / Skill Knowledge
        career_identifier = career or role or job_description
        if not career_identifier:
            frappe.throw("Parameter 'career' or 'role' is required.", frappe.ValidationError)

        from job_search_ai.agents.skill_agent.schemas import SkillProfile

        if isinstance(career_identifier, str):
            # Check if it is a valid career in Career Knowledge or Career Path DocType to raise DoesNotExistError for unknown roles
            if not frappe.db.exists("Career Knowledge", {"career_name": career_identifier}) and \
               not frappe.db.exists("Career Knowledge", {"career_name": ["like", f"%{career_identifier}%"]}) and \
               not frappe.db.exists("Career Path", career_identifier):
                frappe.throw(f"Career '{career_identifier}' not found in Skill Knowledge.", frappe.DoesNotExistError)

            # Prioritize Career Path template first, as it contains curated educational curriculum
            if frappe.db.exists("Career Path", career_identifier):
                logger.info("SkillGapService: loading directly from Career Path '%s' to bypass SkillAgent", career_identifier)
                prereqs = frappe.get_all(
                    "Prerequisite Skills",
                    filters={"parent": career_identifier, "parentfield": "prerequisite_skills"},
                    fields=["prerequisite_skills"]
                )
                foundation = [p.prerequisite_skills for p in prereqs if p.prerequisite_skills]
                
                milestones_std = frappe.get_all(
                    "Path Milestone",
                    filters={"parent": career_identifier, "parentfield": "path_milestone"},
                    fields=["skill", "category"]
                )
                
                core_domain = []
                industry = []
                emerging = []
                for m_std in milestones_std:
                    sname = m_std.skill
                    category = m_std.category or "Core Domain"
                    if not sname:
                        continue
                    if category == "Core Domain":
                        core_domain.append(sname)
                    elif category == "Industry":
                        industry.append(sname)
                    elif category == "Emerging":
                        emerging.append(sname)
                    else:
                        core_domain.append(sname)
                        
                skill_profile = SkillProfile(
                    role_name=career_identifier,
                    foundation_skills=foundation,
                    core_domain_skills=core_domain,
                    industry_skills=industry,
                    emerging_skills=emerging,
                    similarity=1.0,
                    source="db_career_path"
                )
            else:
                ck_name = frappe.db.get_value("Career Knowledge", {"career_name": career_identifier, "active": 1}, "name")
                if not ck_name:
                    ck_name = frappe.db.get_value("Career Knowledge", {"career_name": ["like", f"%{career_identifier}%"], "active": 1}, "name")
                
                if ck_name:
                    logger.info("SkillGapService: loading directly from Career Knowledge '%s' to bypass SkillAgent", ck_name)
                    doc = frappe.get_doc("Career Knowledge", ck_name)
                    foundation = []
                    core_domain = []
                    industry = []
                    emerging = []
                    for s in (doc.skills or []):
                        sname = s.get("skill_name")
                        stype = s.get("skill_type") or "Required"
                        if not sname:
                            continue
                        if stype == "Required":
                            core_domain.append(sname)
                        elif stype in ("Preferred", "Advanced"):
                            industry.append(sname)
                        elif stype == "Foundation":
                            foundation.append(sname)
                        else:
                            emerging.append(sname)
                    skill_profile = SkillProfile(
                        role_name=doc.career_name or career_identifier,
                        foundation_skills=foundation,
                        core_domain_skills=core_domain,
                        industry_skills=industry,
                        emerging_skills=emerging,
                        similarity=1.0,
                        source="db_knowledge"
                    )
                else:
                    from job_search_ai.agents.skill_agent.skill_agent import SkillAgent
                    from job_search_ai.agents.skill_agent.schemas import SkillRequest
                    agent = SkillAgent()
                    request = SkillRequest(role=career_identifier)
                    result = agent.run(request, save_to_doctype=False)
                    skill_profile = result.profile
        elif isinstance(career_identifier, SkillProfile):
            skill_profile = career_identifier
        elif isinstance(career_identifier, dict):
            skill_profile = SkillProfile(
                role_name=career_identifier.get("role_name") or career_identifier.get("role") or "",
                foundation_skills=career_identifier.get("foundation_skills") or [],
                core_domain_skills=career_identifier.get("core_domain_skills") or [],
                industry_skills=career_identifier.get("industry_skills") or [],
                emerging_skills=career_identifier.get("emerging_skills") or [],
            )
        else:
            frappe.throw("Invalid career profile format.", frappe.ValidationError)

        career_title = skill_profile.role_name
        foundation = skill_profile.foundation_skills
        core_domain = skill_profile.core_domain_skills
        industry = skill_profile.industry_skills
        emerging = skill_profile.emerging_skills

        # 3. Canonicalize skill names before deterministic comparison
        canonical_inputs = self.matcher.canonicalize_inputs(
            student_skills=student_skills,
            foundation_skills=foundation,
            core_domain_skills=core_domain,
            industry_skills=industry,
            emerging_skills=emerging,
        )

        # 4. Delegate to pure Python analyzer
        report = self.analyzer.analyze(
            student_identifier=student,
            career_title=career_title,
            student_skills=canonical_inputs.student_skills,
            foundation_skills=canonical_inputs.foundation_skills,
            core_domain_skills=canonical_inputs.core_domain_skills,
            industry_skills=canonical_inputs.industry_skills,
            emerging_skills=canonical_inputs.emerging_skills,
            readiness_threshold=effective_threshold,
        )

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        logger.info(
            "SkillGapService: report generated in %.2fms for student=%s career=%s",
            elapsed_ms,
            student,
            career_title,
        )

        return report

    def fetch_verified_student_skills(self, student_identifier: str) -> List[StudentSkillItem]:
        """
        Fetch verified student skills (ai_verified = 1) from Student Skill DocType.
        Ignore unverified skills (ai_verified = 0).
        """
        if not student_identifier:
            return []

        resolved_student = self._resolve_student_docname(student_identifier)
        if not resolved_student:
            logger.warning("Student not found for identifier: %s", student_identifier)
            return []

        try:
            records = frappe.get_all(
                "Student Skill",
                filters={
                    "student": resolved_student,
                    "ai_verified": 1,
                },
                fields=["skill", "current_level"],
            )
        except Exception as exc:
            logger.error("Error fetching Student Skill for %s: %s", resolved_student, exc)
            return []

        items: List[StudentSkillItem] = []
        seen_skills: set[str] = set()

        for rec in records:
            skill_name = rec.get("skill")
            if not skill_name:
                continue
            
            normalized_name = normalize_skill(skill_name)
            key = normalized_name.lower().strip()

            if key and key not in seen_skills:
                seen_skills.add(key)
                items.append(
                    StudentSkillItem(
                        skill=normalized_name,
                        current_level=rec.get("current_level") or "Intermediate",
                    )
                )

        return items

    def _resolve_student_docname(self, student_identifier: str) -> str:
        """
        Resolve student email or ID to Student DocType primary key.
        """
        if frappe.db.exists("Student", student_identifier):
            return student_identifier

        doc_name = frappe.db.get_value("Student", {"email_id": student_identifier}, "name")
        if doc_name:
            return doc_name

        return student_identifier


