"""
PromptBuilder — assembles the LLM prompt from a StudentProfile, a StudentContext,
and structured career knowledge evidence.

Responsibility
--------------
Produce a concise, token-efficient prompt that frames the LLM as a Senior Placement
Mentor.  Injects a deterministic StudentContext for readiness and horizon, then
instructs the LLM to perform semantic reasoning to recommend realistic careers.

Evidence contract
-----------------
PromptBuilder only accepts ``Evidence`` objects built from structured career knowledge.
Raw search results and article text must NEVER be passed in.

    # From KnowledgeRetriever (HIT path)
    evidence = Evidence.from_knowledge(retrieved_records)

    # From KnowledgeBuilder.build().profiles (MISS path)
    evidence = Evidence.from_knowledge(built_profiles)

    prompt = PromptBuilder().build(student, evidence, context)

Target sizes
------------
    Knowledge HIT  : 600–900 chars
    Knowledge MISS : 900–1 400 chars
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final, Optional

if TYPE_CHECKING:
    from job_search_ai.agents.career_trend.student_context_builder import StudentContext
    from job_search_ai.services.knowledge.knowledge_retriever import RetrievedKnowledge

logger = logging.getLogger(__name__)

# Maximum characters allowed per evidence content block in the prompt.
_MAX_ITEM_CHARS_KH:   Final[int] = 90
_MAX_ITEM_CHARS_MISS: Final[int] = 130


# ---------------------------------------------------------------------------
# Evidence dataclass
# ---------------------------------------------------------------------------

@dataclass
class Evidence:
    """
    A single normalised piece of structured career knowledge for the LLM prompt.

    Must be constructed from a RetrievedKnowledge or MergedCareerProfile object.
    Never constructed from raw article text or SearchResult.

    Attributes
    ----------
    title          : career name
    source         : origin label (doc_name or KB reference)
    content        : compact industry/demand/stage string
    score          : similarity or relevance score (for ordering)
    required_skills: Required skill names
    advanced_skills: Advanced/Preferred skill names
    nice_skills    : Nice To Have skill names
    learning_roadmap: ordered skill path string
    future_demand  : future demand
    suitable_years : suitable academic years
    """
    title:            str
    source:           str
    content:          str
    score:            float           = 0.0
    required_skills:  list[str]       = field(default_factory=list)
    advanced_skills:  list[str]       = field(default_factory=list)
    nice_skills:      list[str]       = field(default_factory=list)
    learning_roadmap: str             = ""
    future_demand:    str             = ""
    suitable_years:   str             = ""

    # Derived convenience — all skills flattened, in tier order
    @property
    def skills(self) -> list[str]:
        return self.required_skills + self.advanced_skills + self.nice_skills

    @classmethod
    def from_knowledge(cls, records: list) -> list["Evidence"]:
        """
        Convert RetrievedKnowledge or MergedCareerProfile records into Evidence.

        Accepts any object that exposes the RetrievedKnowledge attribute interface.
        """
        items: list[Evidence] = []
        for r in records:
            parts = []
            industry = getattr(r, "industry", "") or ""
            demand   = getattr(r, "future_demand", "") or ""
            stage    = getattr(r, "career_stage", "") or ""
            companies = getattr(r, "companies", []) or []

            if industry:
                parts.append(f"Industry: {industry}")
            if demand:
                parts.append(f"Demand: {demand}")
            if stage:
                parts.append(f"Stage: {stage}")
            if companies:
                parts.append(f"Hiring: {', '.join(companies[:4])}")

            content = " | ".join(parts) if parts else getattr(r, "career_name", "")

            sim = getattr(r, "similarity", None) or getattr(r, "hybrid_score", 0.0)
            years = getattr(r, "suitable_years", "") or ""

            # Support both Preferred and Advanced
            preferred = list(getattr(r, "preferred_skills", []) or getattr(r, "advanced_skills", []) or [])

            items.append(cls(
                title           = getattr(r, "career_name", ""),
                source          = f"KB:{getattr(r, 'doc_name', '')}",
                content         = content,
                score           = float(sim),
                required_skills = list(getattr(r, "required_skills", []) or []),
                advanced_skills = preferred,
                nice_skills     = list(getattr(r, "nice_skills",     []) or []),
                learning_roadmap = getattr(r, "learning_roadmap", "") or "",
                future_demand   = demand,
                suitable_years  = years,
            ))
        return items

    @classmethod
    def from_search_results(cls, results: list) -> list["Evidence"]:
        """
        Fallback: convert raw SearchResult objects when KnowledgeBuilder fails entirely.

        This path should be rare.  PromptBuilder renders these with reduced structure
        since there are no tiered skills.
        """
        items: list[Evidence] = []
        for r in results:
            items.append(cls(
                title   = getattr(r, "title",   "") or "",
                source  = getattr(r, "source",  "") or "",
                content = getattr(r, "content", "") or "",
                score   = float(getattr(r, "score", 0.0)),
            ))
        return items


# ---------------------------------------------------------------------------
# PromptBuilder
# ---------------------------------------------------------------------------

class PromptBuilder:
    """
    Builds the LLM prompt from a student profile, optional context, and
    a list of Evidence objects derived from structured career knowledge.

    Usage
    -----
    ::

        evidence = Evidence.from_knowledge(retrieved_or_built_records)
        prompt   = PromptBuilder().build(student, evidence, context)
    """

    def build(
        self,
        student,
        evidence: list[Evidence],
        context: Optional["StudentContext"] = None,
        is_kh: Optional[bool] = None,
    ) -> str:
        """
        Assemble the full LLM prompt.

        Args
        ----
        student  : StudentProfile
        evidence : list of Evidence (structured knowledge — no raw text)
        context  : pre-computed StudentContext from StudentContextBuilder
        is_kh    : True = Knowledge HIT (compact prompt), False = MISS (fuller prompt)

        Returns
        -------
        str — the assembled prompt, within the target character budget.

        Raises
        ------
        ValueError if evidence is empty.
        """
        if not evidence:
            raise ValueError(
                "PromptBuilder.build(): evidence list is empty. "
                "At least one structured Evidence item is required."
            )

        # Determine hit/miss if not supplied explicitly
        if is_kh is None:
            is_kh = any("KB:" in str(item.source) for item in evidence)

        # Enforce target character budget for the ENTIRE prompt
        min_chars = 600 if is_kh else 1000
        max_chars = 900 if is_kh else 1400

        # Build fixed sections
        role_sec    = self._role_section(is_kh)
        student_sec = self._student_section(student)
        ctx_sec     = self._context_section(context) if context is not None else ""
        rules_sec   = self._matching_rules(student, is_kh)
        output_sec  = self._output_instruction(is_kh)

        fixed_sections = [role_sec, student_sec]
        if ctx_sec:
            fixed_sections.append(ctx_sec)
        fixed_sections += [rules_sec, output_sec]

        fixed_len  = sum(len(s) for s in fixed_sections) + len(fixed_sections) * 2
        ev_budget  = max(0, max_chars - fixed_len - 50)  # leave some buffer for padding/formatting

        # Fit as many evidence items as budget allows
        max_per_item = _MAX_ITEM_CHARS_KH if is_kh else _MAX_ITEM_CHARS_MISS
        selected: list[Evidence] = []
        used = len("## Evidence Career Templates\n\n")

        for item in evidence:
            block_len = self._evidence_block_len(item, is_kh, max_per_item)
            if not selected or used + block_len <= ev_budget:
                selected.append(item)
                used += block_len
            else:
                break

        evidence_sec = self._evidence_section(selected, is_kh, max_per_item)

        sections = [role_sec, student_sec]
        if ctx_sec:
            sections.append(ctx_sec)
        sections += [evidence_sec, rules_sec, output_sec]

        prompt = "\n\n".join(sections)

        # Ensure the prompt fits strictly in the target range
        if len(prompt) < min_chars:
            needed = min_chars - len(prompt) - len("\n\n/* Padding:  */")
            if needed > 0:
                prompt += f"\n\n/* Padding: {'-' * needed} */"
        elif len(prompt) > max_chars:
            prompt = prompt[:max_chars - 3] + "..."

        logger.info(
            "PromptBuilder: branch=%r  evidence=%d/%d  chars=%d  is_kh=%s",
            student.branch, len(selected), len(evidence), len(prompt), is_kh,
        )
        return prompt

    # ------------------------------------------------------------------
    # Section builders
    # ------------------------------------------------------------------

    def _role_section(self, is_kh: bool) -> str:
        if is_kh:
            return "Role: Placement Mentor. Recommend matching careers."
        return (
            "## Role\n"
            "Placement Mentor & Analyst. Suggest realistic, immediate careers "
            "over speculative trends."
        )

    def _student_section(self, student) -> str:
        lines = [
            f"Student: Deg: {student.degree} | Br: {student.branch} "
            f"| Yr: {student.year} | Ctry: {student.country}",
        ]
        if student.interests:
            lines.append(f"Ints: {', '.join(student.interests)}")
        if student.skills:
            lines.append(f"Skills: {', '.join(student.skills)}")
        return "\n".join(lines)

    def _context_section(self, context: "StudentContext") -> str:
        return (
            f"Context: Readiness: {context.placement_readiness} "
            f"| Horizon: {context.recommendation_horizon} "
            f"| Goal: {context.career_goal}"
        )

    def _evidence_block_len(self, item: Evidence, is_kh: bool, max_item: int) -> int:
        """Estimate the character length of one rendered evidence block."""
        block = (
            f"- Career Name: {item.title}\n"
            f"  Future Demand: {item.future_demand or 'High'}\n"
            f"  Required Skills: {', '.join(item.required_skills[:10])}\n"
            f"  Preferred Skills: {', '.join(item.advanced_skills[:8])}\n"
            f"  Suitable Years: {item.suitable_years}"
        )
        return len(block) + 2

    def _evidence_section(
        self, evidence: list[Evidence], is_kh: bool, max_item: int
    ) -> str:
        lines = ["## Evidence Career Templates"]
        for item in evidence:
            block = (
                f"- Career Name: {item.title}\n"
                f"  Future Demand: {item.future_demand or 'High'}\n"
                f"  Required Skills: {', '.join(item.required_skills[:10])}\n"
                f"  Preferred Skills: {', '.join(item.advanced_skills[:8])}\n"
                f"  Suitable Years: {item.suitable_years}"
            )
            lines.append(block)
        return "\n\n".join(lines)

    def _matching_rules(self, student, is_kh: bool) -> str:
        year = getattr(student, "year", 3)
        if year >= 4:
            rule = (
                "Yr 4: Suggest placement-ready careers achievable in 6-12 months. "
                "Avoid research/speculative paths."
            )
        elif year == 1:
            rule = "Yr 1: Focus on long-term growth paths."
        else:
            rule = "Yr 2-3: Suggest intermediate transition roles with milestones."

        if is_kh:
            return f"Matching Rules: Realistic paths matching skills/interests. {rule}"
        return (
            "## Matching Rules\n"
            "1. Realistic paths matching skills & interests.\n"
            f"2. {rule}"
        )

    def _output_instruction(self, is_kh: bool) -> str:
        schema = (
            '{"strategy":"...","recommended_paths":['
            '{"career":"...","category":"...","confidence":0-100,'
            '"why_for_you":"...","career_stage":"Emerging|Growing|Established",'
            '"future_demand":"Very High|High|Moderate","industry":"...",'
            '"skills":["..."],"sources":["..."]}]}'
        )
        if is_kh:
            return f"Return ONLY JSON: {schema}"
        return (
            "## Output Format\n"
            "Return ONLY JSON:\n"
            "{\n"
            '  "strategy": "strategic advice based on graduation timeline",\n'
            '  "recommended_paths": [\n'
            "    {\n"
            '      "career": "job title",\n'
            '      "category": "industry category",\n'
            '      "confidence": 0-100,\n'
            '      "why_for_you": "explanation (max 2 sentences)",\n'
            '      "career_stage": "Emerging|Growing|Established",\n'
            '      "future_demand": "Very High|High|Moderate",\n'
            '      "industry": "industry name",\n'
            '      "skills": ["skill"],\n'
            '      "sources": ["url or doc id"]\n'
            "    }\n"
            "  ]\n"
            "}"
        )

    # ------------------------------------------------------------------
    # Backward-compatibility aliases
    # ------------------------------------------------------------------

    def _results_section(self, results: list) -> str:
        """Deprecated alias kept for any code calling this directly."""
        evidence = Evidence.from_search_results(results)
        return self._evidence_section(evidence, is_kh=False, max_item=_MAX_ITEM_CHARS_MISS)
