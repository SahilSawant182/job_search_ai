from __future__ import annotations

import json
from dataclasses import dataclass, asdict

from job_search_ai.agents.job_description.schemas import JobDescriptionRequest, RoleProfile


@dataclass
class Evidence:
    """Structured knowledge handed to the prompt — never raw search results."""
    role_name: str
    summary: str
    responsibilities: list[str]
    required_skills: list[str]
    preferred_skills: list[str]
    qualifications: list[str]
    tools_and_tech: list[str]

    @staticmethod
    def from_profiles(profiles: list[RoleProfile]) -> list["Evidence"]:
        return [
            Evidence(
                role_name=p.role_name,
                summary=p.summary,
                responsibilities=p.responsibilities,
                required_skills=p.required_skills,
                preferred_skills=p.preferred_skills,
                qualifications=p.qualifications,
                tools_and_tech=p.tools_and_tech,
            )
            for p in profiles
        ]


class PromptBuilder:
    """Builds the single LLM prompt that produces the final job description."""

    def build(
        self,
        request: JobDescriptionRequest,
        evidence: list[Evidence],
        max_chars: int = 4000,
    ) -> str:
        evidence_payload = [asdict(e) for e in evidence]

        header = (
            "You are an expert technical recruiter. Write a clear, accurate, "
            "non-generic job description. Respond with ONLY a JSON object — "
            "no markdown, no preamble, no code fences.\n\n"
            f"Role: {request.role}\n"
            f"Seniority: {request.seniority or 'unspecified'}\n"
            f"Department: {request.department or 'unspecified'}\n"
            f"Company: {request.company_name or 'unspecified'}\n"
            f"Company summary: {request.company_summary or 'none provided'}\n"
            f"Location: {request.location or 'unspecified'}\n"
            f"Employment type: {request.employment_type or 'Full-time'}\n"
        )

        if request.must_have_skills:
            header += f"Must-have skills (include verbatim): {', '.join(request.must_have_skills)}\n"
        if request.nice_to_have_skills:
            header += f"Nice-to-have skills (include verbatim): {', '.join(request.nice_to_have_skills)}\n"

        instructions = (
            "\nUsing the research evidence below, output a single JSON object with "
            "exactly these keys: title, summary, responsibilities (list of strings), "
            "required_skills (list of strings), preferred_skills (list of strings), "
            "qualifications (list of strings).\n"
            "Ground every responsibility and skill in the evidence where possible. "
            "Do not invent unrelated technologies. Keep responsibilities action-oriented "
            "(start with a verb).\n\n"
            f"Research evidence:\n{json.dumps(evidence_payload, indent=2)}\n"
        )

        prompt = header + instructions
        if len(prompt) > max_chars:
            prompt = prompt[:max_chars]
        return prompt