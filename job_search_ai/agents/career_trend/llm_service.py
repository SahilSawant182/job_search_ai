"""
LLMService — Integration with LLM provider (OmniRoute or Ollama/Qwen).

Architecture:
    job_search_ai -> LLMService -> [OmniRoute (OpenAI SDK) OR Ollama (urllib)]

Responsibility:
    Accept a prompt string, call the configured model via the active provider,
    parse the JSON output, and return a CareerTrendResponse.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone

from openai import OpenAI, OpenAIError

from job_search_ai.agents.career_trend.schemas import (
    CareerRecommendation,
    CareerTrendResponse,
)
from job_search_ai.services.settings_service import SettingsService

logger = logging.getLogger(__name__)


class LLMServiceError(Exception):
    """
    Raised when the LLM call fails (network error, timeout, or malformed JSON).
    """


class LLMService:
    """
    LLM integration that converts a prompt into a CareerTrendResponse.
    """

    def __init__(self, model_name: str | None = None):
        """
        Initialize the LLM backend.

        Supported providers:

        - omniroute
            Routes requests through a local OmniRoute gateway.
            Intended primarily for local development, testing,
            provider routing and failover.

        - ollama
            Uses the original local Ollama/Qwen endpoint.
            This remains the default backend.

        The backend is selected using the LLM_PROVIDER
        environment variable.
        """
        settings = SettingsService.get()
        provider = (settings.llm_provider or "ollama").lower().strip()

        SUPPORTED_PROVIDERS = {"ollama", "omniroute"}

        if provider not in SUPPORTED_PROVIDERS:
            raise RuntimeError(
                f"Unsupported LLM_PROVIDER='{provider}'. "
                f"Supported values are: {', '.join(sorted(SUPPORTED_PROVIDERS))}."
            )

        self.use_omniroute = provider == "omniroute"

        if self.use_omniroute:
            api_key = os.getenv("OMNIROUTE_API_KEY")
            if not api_key:
                import frappe
                if frappe.local and getattr(frappe.local, "initialised", False):
                    api_key = frappe.conf.get("omniroute_api_key")
            if not api_key:
                raise RuntimeError("OMNIROUTE_API_KEY environment variable or omniroute_api_key in site_config.json is not configured.")
            base_url = settings.omniroute_base_url or "http://localhost:20128/v1"
            self.model_name = model_name or settings.omniroute_model or "career-agent"
            self.client = OpenAI(base_url=base_url, api_key=api_key)
        else:
            self.model_name = model_name or settings.default_llm_model
            self.client = None


    def generate(self, prompt: str, recommendations: list[CareerRecommendation]) -> CareerTrendResponse:
        """
        Send the prompt to LLM and parse the structured response.
        """
        if not prompt or not prompt.strip():
            raise ValueError("LLMService.generate requires a non-empty prompt.")

        raw_response_str = self._call_llm(prompt)

        logger.info("Parsing JSON")
        raw_response_str = self._clean_json_string(raw_response_str)
        try:
            parsed_json = json.loads(raw_response_str)
        except json.JSONDecodeError:
            logger.warning("Response is not valid JSON. Attempting automatic repair.")
            raw_response_str = self._attempt_repair(raw_response_str)
            raw_response_str = self._clean_json_string(raw_response_str)
            try:
                parsed_json = json.loads(raw_response_str)
            except json.JSONDecodeError as final_exc:
                raise LLMServiceError(
                    f"LLM response failed to parse as JSON even after repair attempt. "
                    f"Raw response: {raw_response_str}"
                ) from final_exc

        return self._parse_response(parsed_json, recommendations)

    def _call_llm(self, prompt: str) -> str:
        """Call LLM with retry logic."""
        settings = SettingsService.get()
        timeout = settings.llm_timeout_seconds
        retries = settings.retry_count
        max_attempts = retries + 1

        if self.use_omniroute:
            for attempt in range(1, max_attempts + 1):
                try:
                    logger.info("Calling LLM")
                    response = self.client.chat.completions.create(
                        model=self.model_name,
                        messages=[{"role": "user", "content": prompt}],
                        response_format={"type": "json_object"},
                        timeout=timeout,
                    )
                    logger.info("LLM Success")
                    return response.choices[0].message.content or ""
                except OpenAIError as exc:
                    logger.warning("LLM Failed: %s", exc)
                    if attempt == max_attempts:
                        raise LLMServiceError(f"LLM request failed after {max_attempts} attempts: {exc}") from exc
        else:
            endpoint = settings.ollama_endpoint
            payload = {
                "model": self.model_name,
                "prompt": prompt,
                "stream": False,
                "format": "json",
            }
            req = urllib.request.Request(
                endpoint,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            for attempt in range(1, max_attempts + 1):
                try:
                    logger.info("Calling LLM")
                    with urllib.request.urlopen(req, timeout=timeout) as response:
                        if response.status != 200:
                            raise RuntimeError(f"Ollama API responded with HTTP status {response.status}")
                        body = response.read().decode("utf-8")
                        logger.info("LLM Success")
                        return json.loads(body).get("response", "").strip()
                except Exception as exc:
                    logger.warning("LLM Failed: %s", exc)
                    if attempt == max_attempts:
                        raise LLMServiceError(f"LLM request failed after {max_attempts} attempts: {exc}") from exc
        return ""

    def _attempt_repair(self, malformed_response: str) -> str:
        """Request the model to fix its response to match the exact JSON schema."""
        repair_prompt = (
            "The previous response was not valid JSON. "
            "Return ONLY valid JSON matching this schema, with no explanations, no markdown codeblocks, and no trailing commas:\n\n"
            "{\n"
            '  "strategy": "<one paragraph of overall strategic advice>",\n'
            '  "recommended_paths": [\n'
            "    {\n"
            '      "career": "<exact job title from the provided Evidence Career Templates>",\n'
            '      "why_for_you": "<explanation of why suitable>"\n'
            "    }\n"
            "  ]\n"
            "}\n\n"
            f"Previous Response:\n{malformed_response}"
        )
        try:
            return self._call_llm(repair_prompt)
        except Exception as exc:
            raise LLMServiceError(f"LLM repair attempt failed: {exc}") from exc

    def _clean_json_string(self, text: str) -> str:
        """Strip markdown fences if the LLM output was wrapped in them."""
        text = text.strip()
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        return text.strip()

    def _parse_response(self, raw: dict, recommendations: list[CareerRecommendation]) -> CareerTrendResponse:
        """Convert the parsed JSON dictionary and merge with the python-ranked recommendations."""
        try:
            # Create a lookup for python recommendations
            rec_lookup = {r.career.lower().strip(): r for r in recommendations}
            
            for path in raw.get("recommended_paths", []):
                career_name = str(path.get("career", "")).lower().strip()
                why_for_you = str(path.get("why_for_you", "")).strip()
                
                # Try exact/cleaned match
                if career_name in rec_lookup:
                    rec_lookup[career_name].why_for_you = why_for_you
                else:
                    # Try fallback matching (e.g. substring or first word)
                    matched = False
                    for k, rec in rec_lookup.items():
                        if k in career_name or career_name in k:
                            rec.why_for_you = why_for_you
                            matched = True
                            break
                    # If still not matched, just apply to the first one that has no why_for_you
                    if not matched:
                        for rec in recommendations:
                            if not rec.why_for_you:
                                rec.why_for_you = why_for_you
                                break

            # Ensure every recommendation has a why_for_you
            for rec in recommendations:
                if not rec.why_for_you:
                    rec.why_for_you = f"This path is a strong match for your skills in {', '.join(rec.skills[:3]) if rec.skills else 'your area'} and matches your academic background."

            strategy = raw.get("strategy", "")
            if not strategy:
                strategy = "No overall strategy provided."

            return CareerTrendResponse(
                recommended_paths=recommendations,
                strategy=strategy,
                generated_at=datetime.now(tz=timezone.utc),
            )
        except Exception as exc:
            raise LLMServiceError(
                f"Failed to parse LLM response dict and merge with recommendations: {exc}. "
                f"Raw data: {raw}"
            ) from exc
