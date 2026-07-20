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
            "You are a technical career expert. Generate the complete technical skill hierarchy required "
            f"for the role: {role} (Seniority: {seniority or 'unspecified'}).\n\n"
            "CRITICAL RULES:\n"
            "1. NO soft or generic skills (e.g. Communication, Teamwork, Leadership, Problem Solving, Time Management, SDLC).\n"
            "2. NO unrelated domains or technologies (e.g., no AutoCAD or BIM for software roles, no Kubernetes for civil engineers).\n"
            "3. NO duplicate skills. Prefer specific technologies over generic terms.\n"
            "4. LEARNING ORDER: Within each category, order skills exactly from easiest/prerequisite to most advanced.\n"
            "5. EXHAUSTIVE: List all important technical skills. Do not summarize or shorten.\n"
            "6. NO explanation or prose. Return ONLY JSON.\n\n"
            "Categories:\n"
            "- foundation_skills: Prerequisite concepts and fundamentals beginners must learn first.\n"
            "- core_domain_skills: Technologies and tools used daily in this profession.\n"
            "- industry_skills: Tools and practices commonly expected by real companies (e.g. CI/CD, Docker, testing).\n"
            "- emerging_skills: Modern/emerging technologies that improve employability.\n\n"
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