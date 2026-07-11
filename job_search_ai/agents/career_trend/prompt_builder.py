"""
PromptBuilder — assembles the LLM prompt from a StudentProfile, a StudentContext,
and search results.

Responsibility:
    Produce a concise prompt that frames the LLM as a Senior Placement Mentor
    and Labour Market Analyst. It injects a deterministic StudentContext containing
    readiness and horizon, then instructs the LLM to perform semantic reasoning to
    recommend realistic, achievable careers matching the student's profile.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Final, Optional       

from job_search_ai.agents.career_trend.schemas import SearchResult, StudentProfile

if TYPE_CHECKING:
    from job_search_ai.agents.career_trend.student_context_builder import StudentContext

logger = logging.getLogger(__name__)

# Maximum characters of content to include per search result.
_MAX_CONTENT_CHARS: Final[int] = 220


class PromptBuilder:
    """
    Builds the LLM prompt combining a student's profile, deterministic context,
    and market evidence.
    """

    def build(
        self,
        student: StudentProfile,
        results: list[SearchResult],
        context: Optional["StudentContext"] = None,
    ) -> str:
        """
        Assemble the full LLM prompt.

        Args:
            student: The student whose profile should frame the analysis.
            results: Filtered search results to include as market evidence.
            context: Pre-computed StudentContext from StudentContextBuilder.

        Returns:
            A multi-line prompt string.

        Raises:
            ValueError: If ``results`` is empty.
        """
        if not results:
            raise ValueError(
                "PromptBuilder.build requires at least one SearchResult; received empty list."
            )

        logger.info(
            "Building prompt for student branch=%r with %d search results. Context: %s",
            student.branch,
            len(results),
            "provided" if context else "not provided",
        )

        sections: list[str] = [
            self._role_section(),
            self._student_section(student),
        ]

        if context is not None:
            sections.append(self._context_section(context))

        sections += [
            self._results_section(results),
            self._matching_instructions(student, context),
            self._output_instruction(),
        ]

        prompt = "\n\n".join(sections)
        logger.debug("Prompt length: %d characters.", len(prompt))
        return prompt

    def _role_section(self) -> str:
        return (
            "## Your Role\n"
            "You are an experienced Placement Mentor AND a Labour Market Analyst.\n"
            "Your objective is to recommend the best achievable career paths for the student considering market trends.\n"
            "You must prioritize realistic, immediate, and intermediate career paths over speculative or unrelated global trends."
        )

    def _student_section(self, student: StudentProfile) -> str:
        lines = [
            "## Student Profile",
            f"- Degree: {student.degree}",
            f"- Branch: {student.branch}",
            f"- Year: Year {student.year}",
            f"- Country: {student.country}",
        ]
        if student.interests:
            lines.append(f"- Interests: {', '.join(student.interests)}")
        if student.skills:
            lines.append(f"- Skills: {', '.join(student.skills)}")
        return "\n".join(lines)

    def _context_section(self, context: "StudentContext") -> str:
        return (
            "## Student Context (Deterministic Facts)\n"
            f"- Academic Year: Year {context.academic_year}\n"
            f"- Placement Readiness: {context.placement_readiness}\n"
            f"- Recommendation Horizon: {context.recommendation_horizon}\n"
            f"- Graduation Timeline: {context.graduation_timeline}\n"
            f"- Career Goal: {context.career_goal}"
        )

    def _results_section(self, results: list[SearchResult]) -> str:
        lines = ["## Market Evidence (Search Results)"]
        for idx, result in enumerate(results, start=1):
            content = result.content.strip()
            if len(content) > _MAX_CONTENT_CHARS:
                content = content[:_MAX_CONTENT_CHARS] + "…"
            content = " ".join(content.split())
            lines.append(
                f"### Result {idx}: {result.title}\n"
                f"- Source: {result.source}\n"
                f"- URL: {result.url}\n"
                f"- Summary: {content}"
            )
        return "\n".join(lines)

    def _matching_instructions(self, student: StudentProfile, context: Optional["StudentContext"]) -> str:
        is_year_4 = (student.year >= 4 or student.year <= 0)
        
        weighting = (
            "Skills: 40% · Interests: 30% · Placement Readiness: 20% · Market Trends: 10%"
            if is_year_4
            else "Skills: 30% · Interests: 30% · Placement Readiness: 10% · Market Trends: 30%"
        )

        return (
            "## Career Matching & Reasoning Instructions\n"
            "1. **Infer Primary Career Direction**:\n"
            "   Analyze the student's degree, branch, interests, and skills. Do NOT assume or jump to generic trending titles. Reason carefully.\n"
            "   - Python alone does NOT imply Machine Learning or Data Science. Python is a general-purpose language.\n"
            "   - Look at the complete profile together (e.g. React + HTML + CSS + JavaScript + Frontend Interest -> Frontend/Web track; Spring Boot + Java + SQL -> Backend track).\n\n"
            "2. **Recommendation Progression**:\n"
            "   - Recommendations 1–3 MUST be realistically achievable within approximately one year (or within the student's recommendation horizon).\n"
            "   - Recommendations 4–5 may represent longer-term career evolution (2–4 years ahead) within the same track.\n"
            "   - Example Progression: React Developer -> Next.js Developer -> Frontend Engineer -> Frontend Platform Engineer -> AI Frontend Engineer.\n"
            "   - NEVER recommend careers requiring a complete restart in an unrelated discipline (e.g., advising a Frontend student to become a Quantum Computing Scientist or Cybersecurity Analyst).\n\n"
            "3. **Refinement Weighting Guidance**:\n"
            f"   - Use these reasoning weights to guide your choices: {weighting}.\n"
            "   - Market trends should refine the recommendations; they must never override the student's demonstrated profile.\n\n"
            "4. **Matching Rules (Answer internally before recommending)**:\n"
            "   - Can this student realistically obtain this role within the next 6–12 months (or the recommendation horizon)?\n"
            "   - Does this role naturally extend the student's current skills?\n"
            "   - Does this role align with the student's demonstrated interests?\n"
            "   - Would recommending this career require the student to completely restart in another field?\n"
            "   - If I were mentoring this student personally, would I genuinely recommend this career?\n"
            "   If the answer to any rule is NO, do not recommend it.\n\n"
            "5. **Final Mentor Verification Check**:\n"
            "   Double-check your choices. If you were mentoring this student personally, would you stand behind these careers? If not, pick a better option."
        )

    def _output_instruction(self) -> str:
        return (
            "## Output Format Instructions\n"
            "Based ONLY on the search results and the student's profile context, recommend up to 5 career paths.\n"
            "Do not invent statistics, fabricate trends, or hallucinate skills.\n\n"
            "Rules per recommendation:\n"
            "1. Confidence (0–100): Reflect the authority of the sources and the consistency of the findings.\n"
            "2. Skills: Extract ONLY skills cited in the search results relevant to this role. Do not add generic languages unless specifically mentioned.\n"
            "3. 'why_for_you': Write a personalised paragraph referencing the student's specific skills, interests, year, and graduation timeline. Explain why this is their natural next step.\n"
            "4. career_stage: 'Emerging' | 'Growing' | 'Established'\n"
            "5. future_demand: 'Very High' | 'High' | 'Moderate'\n"
            "6. Do NOT generate learning roadmaps, course recommendations, or resume tips.\n\n"
            "Return ONLY a JSON object — no markdown, no code blocks, no extra text:\n"
            "{\n"
            '  "strategy": "<one paragraph of personalised strategic advice aligned with their graduation timeline>",\n'
            '  "recommended_paths": [\n'
            "    {\n"
            '      "career": "<specific job title>",\n'
            '      "category": "<industry category>",\n'
            '      "confidence": <integer 0-100>,\n'
            '      "why_for_you": "<personalised explanation for THIS student>",\n'
            '      "career_stage": "<Emerging | Growing | Established>",\n'
            '      "future_demand": "<Very High | High | Moderate>",\n'
            '      "industry": "<industry name>",\n'
            '      "skills": ["<skill from search results>"],\n'
            '      "sources": ["<url>"]\n'
            "    }\n"
            "  ]\n"
            "}"
        )
