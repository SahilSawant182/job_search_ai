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
        role: Optional[str] = None,
        job_description: Optional[str] = None,
        readiness_threshold: Optional[float] = None,
    ) -> SkillGapReport:
        """
        Fetch data from Frappe DB and generate structured Skill Gap Report.

        Args:
            student: Student email or Student DocName.
            role: Target role title.
            job_description: Job Description DocName.
            readiness_threshold: Benchmark threshold for job readiness (defaults to Job Search AI Settings).

        Returns:
            SkillGapReport structured output.
        """
        start_time = time.perf_counter()
        effective_threshold = self.get_configured_readiness_threshold(readiness_threshold)

        # Validate student existence
        resolved_student = self._resolve_student_docname(student)
        if not frappe.db.exists("Student", resolved_student):
            frappe.throw(f"Student '{student}' not found.", frappe.DoesNotExistError)

        # Force reload caching layers to ensure database updates are instantly picked up
        from job_search_ai.services.skill_gap.normalizer import initialize_normalization_cache
        from job_search_ai.services.skill_gap.relationship import initialize_relationship_cache
        initialize_normalization_cache(force=True)
        initialize_relationship_cache(force=True)

        # 1. Fetch verified student skills (ai_verified = 1)
        student_skills = self.fetch_verified_student_skills(resolved_student)

        # 2. Fetch required job skills from Job Description DocType
        career_title, primary, advanced, expert = self.fetch_job_skills(
            role=role, job_description=job_description
        )

        # 3. Canonicalize skill names before deterministic comparison
        canonical_inputs = self.matcher.canonicalize_inputs(
            student_skills=student_skills,
            primary_skills=primary,
            advanced_skills=advanced,
            expert_skills=expert,
        )

        # 4. Delegate to pure Python analyzer
        report = self.analyzer.analyze(
            student_identifier=student,
            career_title=career_title,
            student_skills=canonical_inputs.student_skills,
            primary_skills=canonical_inputs.primary_skills,
            advanced_skills=canonical_inputs.advanced_skills,
            expert_skills=canonical_inputs.expert_skills,
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

    def fetch_job_skills(
        self, role: Optional[str] = None, job_description: Optional[str] = None
    ) -> Tuple[str, List[str], List[str], List[str]]:
        """
        Fetch job skills from Job Description DocType.

        Returns:
            Tuple of (career_title, primary_skills, advanced_skills, expert_skills)
        """
        doc = None

        if job_description:
            if frappe.db.exists("Job Description", job_description):
                doc = frappe.get_doc("Job Description", job_description)
            elif not role:
                frappe.throw(f"Job Description '{job_description}' not found.", frappe.DoesNotExistError)

        if not doc and role:
            jd_name = frappe.db.get_value("Job Description", {"role": role}, "name")
            if not jd_name:
                jd_name = frappe.db.get_value(
                    "Job Description", {"role": ["like", f"%{role}%"]}, "name"
                )
            if jd_name:
                doc = frappe.get_doc("Job Description", jd_name)
            else:
                frappe.throw(f"Job Description for Role '{role}' not found.", frappe.DoesNotExistError)

        if not doc:
            frappe.throw("Could not resolve Job Description or Role.", frappe.DoesNotExistError)

        career_title = doc.role or role or doc.name
        primary = parse_skill_string(doc.primary_skills)
        advanced = parse_skill_string(doc.advanced_skills)
        expert = parse_skill_string(doc.expert_skills)

        return career_title, primary, advanced, expert
