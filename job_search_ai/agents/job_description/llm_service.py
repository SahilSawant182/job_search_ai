"""
LLM client for job description generation.

Reads connection details from the `Job Search AI Settings` Single DocType
(same doctype CareerTrendAgent uses), so both agents stay on one
LLM provider configuration.
"""

from __future__ import annotations

import json
import logging

import requests

from job_search_ai.agents.job_description.schemas import JobDescriptionRequest, JobDescriptionResponse

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

    def generate(self, prompt: str, request: JobDescriptionRequest) -> JobDescriptionResponse:
        """Final-stage call: produces the actual JobDescriptionResponse."""
        last_exc: Exception | None = None
        for attempt in range(self.retry_count + 1):
            try:
                raw_text = self.call_raw(prompt)
                return self._parse(raw_text, request)
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                logger.warning("LLMService attempt %d failed: %s", attempt + 1, exc)
        raise LLMServiceError(f"LLM generation failed after retries: {last_exc}") from last_exc

    def call_raw(self, prompt: str) -> str:
        """Low-level call returning raw model text. Reused by JDKnowledgeBuilder
        for the extraction pass, so both stages share retry/timeout config."""
        if self.provider == "omniroute":
            resp = requests.post(
                f"{self.base_url.rstrip('/')}/chat/completions",
                json={
                    "model": self.model_name,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3,
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
                "options": {"temperature": 0.3},
            },
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("response", "")

    def _parse(self, raw_text: str, request: JobDescriptionRequest) -> JobDescriptionResponse:
        cleaned = raw_text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            if cleaned.lower().startswith("json"):
                cleaned = cleaned[4:]
        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise LLMServiceError(
                f"LLM did not return valid JSON: {exc}\nRaw (truncated): {raw_text[:300]}"
            ) from exc

        return JobDescriptionResponse(
            title=payload.get("title") or request.role,
            summary=payload.get("summary", ""),
            responsibilities=payload.get("responsibilities", []),
            required_skills=payload.get("required_skills") or request.must_have_skills,
            preferred_skills=payload.get("preferred_skills") or request.nice_to_have_skills,
            qualifications=payload.get("qualifications", []),
            employment_type=request.employment_type,
            location=request.location,
        )