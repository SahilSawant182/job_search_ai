"""
LLM client for direct skill generation.

No Tavily / web search involved — the model generates the three skill
tiers straight from its own training knowledge, in a single call.
"""

from __future__ import annotations

import json
import logging

import requests

logger = logging.getLogger(__name__)


class LLMServiceError(Exception):
    pass


class LLMService:

    def __init__(self):
        from job_search_ai.services.settings_service import SettingsService
        settings = SettingsService.get()

        self.provider = settings.llm_provider or "ollama"
        self.timeout = int(settings.llm_timeout_seconds or 180)
        self.retry_count = int(settings.retry_count or 1)

        if self.provider == "omniroute":
            self.base_url = settings.omniroute_base_url
            self.model_name = settings.omniroute_model
        else:
            self.base_url = settings.ollama_endpoint
            self.model_name = settings.default_llm_model

    def generate_skills(self, role: str, seniority: str | None = None) -> dict:
        """Returns a dict containing all 8 new skill profile fields."""
        prompt = self._build_prompt(role, seniority)

        last_exc: Exception | None = None
        for attempt in range(self.retry_count + 1):
            try:
                raw_text = self._call(prompt)
                return self._parse(raw_text)
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                logger.warning("LLMService.generate_skills attempt %d failed: %s", attempt + 1, exc)
        raise LLMServiceError(f"Skill generation failed after retries: {last_exc}") from last_exc

    def _build_prompt(self, role: str, seniority: str | None) -> str:
        return (
            "You are a senior Engineering Manager and Technical Curriculum Designer with experience hiring software engineers and designing training programs for new graduates.\n"
            "Your job is NOT to list every technology related to a career.\n"
            "Your job is to generate a single, practical, industry-standard learning curriculum for the requested career.\n"
            "The output will be consumed by a Skill Gap Agent and a Roadmap Agent.\n"
            "Therefore the response must be:\n"
            "* technically accurate\n"
            "* practical\n"
            "* consistent\n"
            "* complete\n"
            "* free of unnecessary alternatives\n\n"
            "--- \n\n"
            "## Career\n"
            f"Role: {role}\n"
            f"Seniority: {seniority or 'Junior'}\n\n"
            "--- \n\n"
            "## Objective\n"
            f"Imagine a student asks: \"I want to become a {role}. What technical skills should I learn?\"\n"
            f"Generate the learning curriculum that would realistically prepare that student for an entry-level or junior position in today's industry.\n"
            "Do NOT generate an encyclopedia. Generate one recommended learning path.\n\n"
            "--- \n\n"
            "# Critical Rules\n"
            "## Rule 1 — Recommend ONE technology stack\n"
            "Do NOT list every possible framework or language. Choose the most practical and widely adopted stack. Choose only ONE based on what best fits the requested career.\n"
            "## Rule 2 — Do NOT mix ecosystems\n"
            "Never combine unrelated technology stacks. Recommend one stack only.\n"
            "## Rule 3 — Skills must be in learning order\n"
            "Every list must be ordered exactly as someone should learn them. Earlier skills must be prerequisites for later skills. Never randomize.\n"
            "## Rule 4 — No duplicate concepts\n"
            "If a framework/concept is already listed (e.g. React), do not also list a generic category (e.g. Frontend Frameworks). Prefer specific technologies.\n"
            "## Rule 5 — Technical skills only\n"
            "Never include soft skills: Communication, Leadership, Teamwork, Problem Solving, Time Management, Critical Thinking, Presentation Skills, Project Management.\n"
            "## Rule 6 — No unrelated technologies\n"
            "Every skill must clearly belong to the requested role.\n"
            "## Rule 7 — Recommend practical industry technologies\n"
            "Prefer technologies that are widely used today. Avoid obsolete technologies.\n\n"
            "--- \n\n"
            "# Skill Categories\n"
            "## foundation_skills\n"
            "Programming fundamentals and prerequisite knowledge (e.g., Programming Logic, Variables, Functions, Object-Oriented Programming, Git Basics, Command Line, HTTP Basics).\n"
            "## core_domain_skills\n"
            "The primary technologies used every day.\n"
            "## industry_skills\n"
            "Technologies commonly expected in professional environments (e.g., Git, GitHub, Docker, CI/CD, Testing, Redis, Monitoring, API Documentation, Performance Optimization, AWS, Logging).\n"
            "## emerging_skills\n"
            "Modern technologies that improve employability but are not mandatory (e.g., Next.js, GraphQL, Serverless, AI-assisted Development, Vector Databases, RAG, MCP, Agentic AI).\n\n"
            "--- \n\n"
            "# Quantity Guidelines\n"
            "Return approximately:\n"
            "- Foundation Skills: 5–8 skills\n"
            "- Core Domain Skills: 10–15 skills\n"
            "- Industry Skills: 5–10 skills\n"
            "- Emerging Skills: 3–6 skills\n"
            "Do not artificially increase the list size. Only include meaningful technologies.\n\n"
            "--- \n\n"
            "# Final Validation\n"
            "Before returning the response, verify:\n"
            "✓ The learning path is coherent.\n"
            "✓ Only one technology stack is recommended.\n"
            "✓ No duplicate skills exist.\n"
            "✓ No unrelated technologies exist.\n"
            "✓ Skills are ordered from beginner to advanced.\n"
            "✓ The curriculum could realistically be followed by a student.\n"
            "✓ The output is useful for generating a learning roadmap.\n\n"
            "--- \n\n"
            "Respond with ONLY a JSON object (no markdown, no preamble) in exactly this shape:\n"
            "{\n"
            f'  "role": "{role}",\n'
            '  "foundation_skills": ["skill1", "skill2", ...],\n'
            '  "core_domain_skills": ["skill1", "skill2", ...],\n'
            '  "industry_skills": ["skill1", "skill2", ...],\n'
            '  "emerging_skills": ["skill1", "skill2", ...]\n'
            "}"
        )

    def _call(self, prompt: str) -> str:
        if self.provider == "omniroute":
            resp = requests.post(
                f"{self.base_url.rstrip('/')}/chat/completions",
                json={
                    "model": self.model_name,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.2,
                },
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]

        resp = requests.post(
            self.base_url,
            json={
                "model": self.model_name,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.2},
            },
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("response", "")

    def _parse(self, raw_text: str) -> dict:
        cleaned = raw_text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            if cleaned.lower().startswith("json"):
                cleaned = cleaned[4:]
            cleaned = cleaned.strip()
        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise LLMServiceError(
                f"LLM did not return valid JSON: {exc}\nRaw (truncated): {raw_text[:300]}"
            ) from exc

        return {
            "role": payload.get("role", ""),
            "foundation_skills": payload.get("foundation_skills", []) or [],
            "core_domain_skills": payload.get("core_domain_skills", []) or [],
            "industry_skills": payload.get("industry_skills", []) or [],
            "emerging_skills": payload.get("emerging_skills", []) or [],
        }     