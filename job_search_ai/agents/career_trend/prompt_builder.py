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
    matched_required_skills: Required skills matched by student
    missing_required_skills: Required skills missing from student
    matched_preferred_skills: Preferred/Advanced skills matched by student
    missing_preferred_skills: Preferred/Advanced skills missing from student
    learning_roadmap: ordered skill path string
    future_demand  : future demand
    suitable_years : suitable academic years
    """
    title:                    str
    source:                   str
    content:                  str
    score:                    float           = 0.0
    required_skills:          list[str]       = field(default_factory=list)
    advanced_skills:          list[str]       = field(default_factory=list)
    nice_skills:              list[str]       = field(default_factory=list)
    matched_required_skills:  list[str]       = field(default_factory=list)
    missing_required_skills:  list[str]       = field(default_factory=list)
    matched_preferred_skills: list[str]       = field(default_factory=list)
    missing_preferred_skills: list[str]       = field(default_factory=list)
    learning_roadmap:         str             = ""
    future_demand:            str             = ""
    suitable_years:           str             = ""
    quality_score:            int             = 70
    confidence:               float           = 0.0
    evidence_count:           int             = 1

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
            req_skills = list(getattr(r, "required_skills", []) or [])
            nice_skills = list(getattr(r, "nice_skills", []) or [])

            items.append(cls(
                title                    = getattr(r, "career_name", ""),
                source                   = f"KB:{getattr(r, 'doc_name', '')}",
                content                  = content,
                score                    = float(sim),
                required_skills          = req_skills,
                advanced_skills          = preferred,
                nice_skills              = nice_skills,
                matched_required_skills  = list(getattr(r, "matched_required_skills", []) or []),
                missing_required_skills  = list(getattr(r, "missing_required_skills", []) or []),
                matched_preferred_skills = list(getattr(r, "matched_preferred_skills", []) or []),
                missing_preferred_skills = list(getattr(r, "missing_preferred_skills", []) or []),
                learning_roadmap         = getattr(r, "learning_roadmap", "") or "",
                future_demand            = demand,
                suitable_years           = years,
                quality_score            = int(getattr(r, "quality_score", 70)),
                confidence               = float(getattr(r, "confidence", 0.0)),
                evidence_count           = int(getattr(r, "evidence_count", 1)),
            ))
        return items


# ---------------------------------------------------------------------------
# PromptBuilder
# ---------------------------------------------------------------------------

class PromptBuilder:
    """
    Builds the LLM prompt from a StudentContext and a list of Evidence objects.

    Usage
    -----
    ::

        evidence = Evidence.from_knowledge(retrieved_or_built_records)
        prompt   = PromptBuilder().build(evidence, context)
    """

    def build(
        self,
        evidence: list[Evidence],
        context: "StudentContext",
        is_kh: Optional[bool] = None,
    ) -> str:
        """
        Assemble the full LLM prompt.

        Args
        ----
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
        student_sec = self._student_section(context)
        ctx_sec     = self._context_section(context)
        rules_sec   = self._matching_rules(context, is_kh)
        output_sec  = self._output_instruction(is_kh)

        fixed_sections = [role_sec, student_sec, ctx_sec, rules_sec, output_sec]

        fixed_len  = sum(len(s) for s in fixed_sections) + len(fixed_sections) * 2
        ev_budget  = max(0, max_chars - fixed_len - 50)  # leave some buffer for padding/formatting

        # Fit as many evidence items as budget allows
        max_per_item = _MAX_ITEM_CHARS_KH if is_kh else _MAX_ITEM_CHARS_MISS
        selected: list[Evidence] = []
        used = len("## Evidence Career Templates\n\n")

        for item in evidence:
            block_len = self._evidence_block_len(item)
            if not selected or used + block_len <= ev_budget:
                selected.append(item)
                used += block_len
            else:
                break

        evidence_sec = self._evidence_section(selected)

        sections = [role_sec, student_sec, ctx_sec, evidence_sec, rules_sec, output_sec]

        prompt = "\n\n".join(sections)

        # Ensure the prompt fits strictly in the target range
        if len(prompt) < min_chars:
            needed = min_chars - len(prompt) - len("\n\n/* Padding:  */")
            if needed > 0:
                prompt += f"\n\n/* Padding: {'-' * needed} */"
        elif len(prompt) > max_chars:
            if prompt.endswith(output_sec):
                prefix = prompt[:-len(output_sec)]
                allowed_prefix_len = max_chars - len(output_sec) - 5
                prompt = prefix[:allowed_prefix_len] + "...\n\n" + output_sec
            else:
                prompt = prompt[:max_chars - 3] + "..."

        logger.info(
            "PromptBuilder: branch=%r  evidence=%d/%d  chars=%d  is_kh=%s",
            context.branch, len(selected), len(evidence), len(prompt), is_kh,
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

    def _student_section(self, context: "StudentContext") -> str:
        lines = [
            f"Student: Deg: {context.degree} | Br: {context.branch} "
            f"| Yr: {context.academic_year} | Ctry: {context.country}",
        ]
        if context.interests:
            lines.append(f"Ints: {', '.join(context.interests)}")
        if context.skills:
            lines.append(f"Skills: {', '.join(context.skills)}")
        return "\n".join(lines)

    def _context_section(self, context: "StudentContext") -> str:
        return (
            f"Context: Readiness: {context.placement_readiness} "
            f"| Horizon: {context.recommendation_horizon} "
            f"| Goal: {context.career_goal}"
        )

    def _render_item(self, item: Evidence) -> str:
        lines = [
            f"- Career Name: {item.title}",
            f"  Quality/Consensus: Quality {item.quality_score}/100 | Evidence Sources: {item.evidence_count} | Confidence: {item.confidence:.2f}",
            f"  Future Demand: {item.future_demand or 'High'}",
        ]
        if item.matched_required_skills:
            lines.append(f"  Matched Required Skills: {', '.join(item.matched_required_skills[:10])}")
        if item.missing_required_skills:
            lines.append(f"  Missing Required Skills: {', '.join(item.missing_required_skills[:10])}")
        if item.matched_preferred_skills:
            lines.append(f"  Matched Preferred Skills: {', '.join(item.matched_preferred_skills[:8])}")
        if item.missing_preferred_skills:
            lines.append(f"  Missing Preferred Skills: {', '.join(item.missing_preferred_skills[:8])}")
        if item.suitable_years:
            lines.append(f"  Suitable Years: {item.suitable_years}")
        if item.learning_roadmap:
            lines.append(f"  Roadmap: {item.learning_roadmap}")
        return "\n".join(lines)

    def _evidence_block_len(self, item: Evidence) -> int:
        """Estimate the character length of one rendered evidence block."""
        return len(self._render_item(item)) + 2

    def _evidence_section(self, evidence: list[Evidence]) -> str:
        lines = ["## Evidence Career Templates"]
        for item in evidence:
            lines.append(self._render_item(item))
        return "\n\n".join(lines)

    def _matching_rules(self, context: "StudentContext", is_kh: bool) -> str:
        rule = getattr(context, "year_matching_rule", "")
        if is_kh:
            return (
                f"Matching Rules: Recommend careers realistically achievable based on the student's current "
                f"skills, interests, and graduation timeline. {rule}"
            )
        return (
            "## Matching Rules\n"
            "1. Recommend careers realistically achievable based on current skills and interests.\n"
            "2. Academic year determines realism: "
            f"{rule}"
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
