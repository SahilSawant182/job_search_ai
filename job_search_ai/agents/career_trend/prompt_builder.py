"""
PromptBuilder — assembles the LLM prompt from a StudentProfile, a StudentContext,
and market evidence (either from the knowledge base or from web search results).

Responsibility:
    Produce a concise prompt that frames the LLM as a Senior Placement Mentor
    and Labour Market Analyst. It injects a deterministic StudentContext containing
    readiness and horizon, then instructs the LLM to perform semantic reasoning to
    recommend realistic, achievable careers matching the student's profile.

Evidence abstraction
--------------------
PromptBuilder is evidence-source-agnostic.  Callers normalise their data into
``Evidence`` objects before passing them in.  The builder does not know (or care)
whether the evidence came from MariaDB (KnowledgeRetriever) or Tavily.

    # From KnowledgeRetriever
    evidence = Evidence.from_knowledge(retrieved_knowledge_list)

    # From Tavily
    evidence = Evidence.from_search_results(filtered_search_results)

    prompt = PromptBuilder().build(student, evidence, context)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final, Optional

from job_search_ai.agents.career_trend.schemas import SearchResult, StudentProfile

if TYPE_CHECKING:
    from job_search_ai.agents.career_trend.student_context_builder import StudentContext
    from job_search_ai.services.knowledge.knowledge_retriever import RetrievedKnowledge

logger = logging.getLogger(__name__)

# Maximum characters of content to include per evidence item in the prompt.
_MAX_CONTENT_CHARS: Final[int] = 220


# ---------------------------------------------------------------------------
# Evidence abstraction
# ---------------------------------------------------------------------------

@dataclass
class Evidence:
    """A single normalised piece of market evidence for the LLM prompt.

    Represents one item regardless of whether it came from the Career Knowledge
    database (KnowledgeRetriever) or from a Tavily web search (SearchResult).

    Attributes
    ----------
    title    : str   — headline or career name
    source   : str   — publisher / origin label
    url      : str   — source URL (empty string if not available)
    content  : str   — summary text shown in the prompt
    score    : float — relevance or similarity score (for ordering)
    skills   : list  — associated skill tags (optional)
    """
    title:   str
    source:  str
    url:     str
    content: str
    score:   float = 0.0
    skills:  list[str] = field(default_factory=list)

 
    @classmethod
    def from_search_results(cls, results: "list[SearchResult]") -> "list[Evidence]":
        """Convert a list of Tavily SearchResult objects into Evidence items."""
        return [
            cls(
                title   = r.title,
                source  = r.source,
                url     = r.url,
                content = r.content,
                score   = r.score,
                skills  = [],
            )
            for r in results
        ]

    @classmethod
    def from_knowledge(cls, records: "list[RetrievedKnowledge]") -> "list[Evidence]":
        """Convert RetrievedKnowledge records into structured Evidence items.

        Phase 9: emits tiered skill blocks so the LLM can produce accurate
        skill-gap analysis and per-tier explanations.
        """
        items = []
        for r in records:
            parts = []
            if r.industry:
                parts.append(f"Industry: {r.industry}")
            if r.future_demand:
                parts.append(f"Demand: {r.future_demand}")
            if r.career_stage:
                parts.append(f"Stage: {r.career_stage}")
            if r.companies:
                parts.append(f"Hiring: {', '.join(r.companies[:4])}")
            content = " | ".join(parts) if parts else r.career_name

            items.append(cls(
                title   = r.career_name,
                source  = f"KB:{r.doc_name}",
                url     = "",
                content = content,
                score   = r.similarity,
                skills  = getattr(r, "required_skills", r.skills[:6]),
                # Pass tier lists as extra attributes via a dict trick on the dataclass
                # PromptBuilder reads these via hasattr
            ))
            # Attach tier data directly to allow PromptBuilder to use it
            items[-1].__dict__["_required"]  = getattr(r, "required_skills", [])
            items[-1].__dict__["_advanced"]  = getattr(r, "advanced_skills", [])
            items[-1].__dict__["_nice"]      = getattr(r, "nice_skills",     [])
            items[-1].__dict__["_roadmap"]   = getattr(r, "learning_roadmap", "")
        return items


# ---------------------------------------------------------------------------
# PromptBuilder
# ---------------------------------------------------------------------------

class PromptBuilder:
    """
    Builds the LLM prompt combining a student's profile, deterministic context,
    and market evidence (from any source).

    Usage
    -----
    ::

        # Evidence from knowledge base
        evidence = Evidence.from_knowledge(retrieved_records)

        # OR evidence from web search
        evidence = Evidence.from_search_results(filtered_results)

        prompt = PromptBuilder().build(student, evidence, context)
    """

    def build(
        self,
        student: StudentProfile,
        results: "list[SearchResult] | list[Evidence]",
        context: Optional["StudentContext"] = None,
    ) -> str:
        """
        Assemble the full LLM prompt.

        Args:
            student: The student whose profile should frame the analysis.
            results: Evidence items — either raw ``SearchResult`` objects (legacy
                     path, auto-converted) or pre-normalised ``Evidence`` objects.
            context: Pre-computed StudentContext from StudentContextBuilder.

        Returns:
            A multi-line prompt string.

        Raises:
            ValueError: If ``results`` is empty.
        """
        if not results:
            raise ValueError(
                "PromptBuilder.build requires at least one evidence item; received empty list."
            )

        # Auto-convert legacy SearchResult list to Evidence list
        if results and isinstance(results[0], SearchResult):
            evidence: list[Evidence] = Evidence.from_search_results(results)
        else:
            evidence = list(results)

        # Determine if this is a Knowledge Hit
        is_kh = any(
            "KB:" in str(item.source) or "Career Knowledge DB" in str(item.source)
            for item in evidence
        )

        # Enforce target character limits (strictly avoids token exhaustion)
        # KH: 600-900 chars target | Miss: 1000-1500 chars target
        if is_kh:
            max_chars = 900
        else:
            max_chars = 1500

        # Build prompt sections
        role_sec = self._role_section(is_kh)
        student_sec = self._student_section(student)
        context_sec = self._context_section(context, is_kh) if context is not None else ""
        matching_instructions_sec = self._matching_instructions(student, context, is_kh)
        output_instruction_sec = self._output_instruction(is_kh)

        base_sections = [role_sec, student_sec]
        if context_sec:
            base_sections.append(context_sec)
        base_sections += [matching_instructions_sec, output_instruction_sec]

        base_prompt_len = sum(len(s) for s in base_sections) + (len(base_sections) - 1) * 2
        evidence_budget = max_chars - base_prompt_len - 20

        # Format and filter evidence items that fit within the budget
        selected_evidence: list[Evidence] = []
        current_evidence_len = len("Evidence:\n\n" if is_kh else "## Market Evidence\n\n")

        for item in evidence:
            content = item.content.strip()
            max_item_chars = 80 if is_kh else 120
            if len(content) > max_item_chars:
                content = content[:max_item_chars] + "…"
            content = " ".join(content.split())

            if is_kh:
                block = f"E: {item.title} ({item.source}) | Summary: {content}"
                if item.skills:
                    block += f" | Skills: {', '.join(item.skills[:3])}"
            else:
                block = (
                    f"### Evidence {len(selected_evidence) + 1}: {item.title}\n"
                    f"- Source: {item.source}\n"
                )
                if item.url:
                    block += f"- URL: {item.url}\n"
                block += f"- Summary: {content}"
                if item.skills:
                    block += f"\n- Key Skills: {', '.join(item.skills[:5])}"

            block_len = len(block) + 2
            if len(selected_evidence) == 0 or (current_evidence_len + block_len <= evidence_budget):
                selected_evidence.append(item)
                current_evidence_len += block_len
            else:
                break

        evidence_sec = self._evidence_section(selected_evidence, is_kh)

        sections: list[str] = [role_sec, student_sec]
        if context_sec:
            sections.append(context_sec)
        sections += [
            evidence_sec,
            matching_instructions_sec,
            output_instruction_sec,
        ]

        prompt = "\n\n".join(sections)
        logger.info(
            "Building prompt for student branch=%r with %d of %d evidence item(s). Length: %d chars (max: %d)",
            student.branch,
            len(selected_evidence),
            len(evidence),
            len(prompt),
            max_chars,
        )
        return prompt

    def _role_section(self, is_kh: bool = False) -> str:
        if is_kh:
            return "Role: Placement Mentor. Recommend matching careers."
        return "## Role\nPlacement Mentor & Analyst. Suggest realistic, immediate careers over speculative trends."

    def _student_section(self, student: StudentProfile) -> str:
        lines = [
            f"Student: Deg: {student.degree} | Br: {student.branch} | Yr: {student.year} | Ctry: {student.country}",
        ]
        if student.interests:
            lines.append(f"Ints: {', '.join(student.interests)}")
        if student.skills:
            lines.append(f"Skills: {', '.join(student.skills)}")
        return "\n".join(lines)

    def _context_section(self, context: "StudentContext", is_kh: bool = False) -> str:
        return f"Context: Readiness: {context.placement_readiness} | Horizon: {context.recommendation_horizon} | Goal: {context.career_goal}"

    def _evidence_section(self, evidence: list[Evidence], is_kh: bool = False) -> str:
        if is_kh:
            lines = ["Evidence:"]
            for item in evidence:
                # Phase 9: structured tiered skill block
                req  = item.__dict__.get("_required", item.skills[:4])
                adv  = item.__dict__.get("_advanced", [])
                nice = item.__dict__.get("_nice",     [])
                road = item.__dict__.get("_roadmap",  "")

                content = item.content.strip()
                if len(content) > 100:
                    content = content[:97] + "…"
                block = f"{item.title} | {content}"
                if req:
                    block += f" | Required: {', '.join(req[:5])}"
                if adv:
                    block += f" | Advanced: {', '.join(adv[:4])}"
                if nice:
                    block += f" | Nice: {', '.join(nice[:3])}"
                lines.append(block)
            return "\n".join(lines)
        else:
            lines = ["## Market Evidence"]
            for idx, item in enumerate(evidence, start=1):
                content = item.content.strip()
                if len(content) > 120:
                    content = content[:117] + "…"
                content = " ".join(content.split())
                block = (
                    f"### Evidence {idx}: {item.title}\n"
                    f"- Source: {item.source}\n"
                )
                if item.url:
                    block += f"- URL: {item.url}\n"
                block += f"- Summary: {content}"
                if item.skills:
                    block += f"\n- Key Skills: {', '.join(item.skills[:5])}"
                lines.append(block)
            return "\n".join(lines)

    # Keep the old name as an alias for backward compatibility with any
    # code that calls _results_section directly (e.g. benchmark tests).
    def _results_section(self, results: "list[SearchResult]") -> str:
        return self._evidence_section(Evidence.from_search_results(results))

    def _matching_instructions(self, student: StudentProfile, context: Optional["StudentContext"], is_kh: bool = False) -> str:
        year = student.year
        if year >= 4:
            rule = "Yr 4: Suggest placement-ready careers achievable in 6-12 months. Avoid research/speculative paths (e.g. Quantum, AI Scientist, Blockchain, Cybersecurity Research)."
        elif year == 1:
            rule = "Yr 1: Focus on long-term growth paths (frontend->fullstack->AI)."
        else:
            rule = "Yr 2-3: Suggest intermediate transition roles with milestones."
        if is_kh:
            return f"Matching Rules: Suggest realistic paths matching skills/interests. {rule}"
        return (
            "## Matching Rules\n"
            "1. Realistic paths matching skills & interests.\n"
            f"2. {rule}"
        )

    def _output_instruction(self, is_kh: bool = False) -> str:
        if is_kh:
            return (
                "Return ONLY JSON: {\"strategy\":\"...\",\"recommended_paths\":[{\"career\":\"...\",\"category\":\"...\",\"confidence\":0-100,\"why_for_you\":\"...\",\"career_stage\":\"Emerging|Growing|Established\",\"future_demand\":\"Very High|High|Moderate\",\"industry\":\"...\",\"skills\":[\"...\"],\"sources\":[\"...\"]}]}"
            )
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
