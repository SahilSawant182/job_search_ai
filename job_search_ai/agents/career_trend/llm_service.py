"""
LLMService — real Qwen LLM integration via Ollama API.

Responsibility:
    Accept a prompt string, call the configured Qwen model via HTTP,
    parse the JSON output, and return a CareerTrendResponse.

Requirements:
    - Calls http://135.181.6.215:11434/api/generate.
    - Configurable models: qwen3:8b, qwen2.5:3b, qwen2.5:1.5b.
    - Model selection priority: constructor parameter -> environment variable -> default (qwen3:8b).
    - Timeout: 180 seconds.
    - Automatic retry once if call fails.
    - Attempt one automatic repair if invalid JSON is returned.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Final

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

    Usage::

        service = LLMService(model_name="qwen2.5:3b")
        response = service.generate(prompt)
    """

    def __init__(self, model_name: str | None = None):
        """
        Initialize LLMService with a specific model name.
        Priority: constructor parameter -> SettingsService -> default model.
        """
        settings = SettingsService.get()
        self.model_name = model_name or settings.default_llm_model

    def generate(self, prompt: str) -> CareerTrendResponse:
        """
        Send the prompt to the configured LLM and parse the structured response.

        Args:
            prompt: The full prompt string produced by PromptBuilder.

        Returns:
            A fully populated CareerTrendResponse.

        Raises:
            LLMServiceError: If the LLM call fails or the response cannot
                             be parsed into the expected schema.
            ValueError: If `prompt` is empty.
        """
        if not prompt or not prompt.strip():
            raise ValueError("LLMService.generate requires a non-empty prompt.")

        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
            "format": "json",
        }

        # Stage 1: Make request (with retry)
        response_data = self._post_request(payload)
        raw_response_str = response_data.get("response", "").strip()

        # Stage 2: Parse and repair if necessary
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

        # Stage 3: Convert JSON to dataclasses
        return self._parse_response(parsed_json)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _post_request(self, payload: dict) -> dict:
        """Post a request to Ollama /api/generate with retry logic configured via SettingsService."""
        settings = SettingsService.get()
        endpoint = settings.ollama_endpoint
        timeout = settings.llm_timeout_seconds
        retries = settings.retry_count
        max_attempts = retries + 1

        req = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        for attempt in range(1, max_attempts + 1):
            try:
                logger.info("Calling LLM: %s (attempt %d/%d)", self.model_name, attempt, max_attempts)
                with urllib.request.urlopen(req, timeout=timeout) as response:
                    if response.status != 200:
                        raise RuntimeError(f"Ollama API responded with HTTP status {response.status}")
                    body = response.read().decode("utf-8")
                    return json.loads(body)
            except Exception as exc:
                logger.warning("Attempt %d/%d failed for model %s: %s", attempt, max_attempts, self.model_name, exc)
                if attempt == max_attempts:
                    raise LLMServiceError(f"Qwen request failed after {max_attempts} attempts: {exc}") from exc

    def _attempt_repair(self, malformed_response: str) -> str:
        """
        Request the model to fix its response to match the exact JSON schema.
        """
        repair_prompt = (
            "The previous response was not valid JSON. "
            "Return ONLY valid JSON matching this schema, with no explanations, no markdown codeblocks, and no trailing commas:\n\n"
            "{\n"
            '  "strategy": "<one paragraph of overall strategic advice>",\n'
            '  "recommended_paths": [\n'
            "    {\n"
            '      "career": "<job title>",\n'
            '      "category": "<category>",\n'
            '      "confidence": <integer 0-100>,\n'
            '      "why_for_you": "<explanation of why suitable and future demand>",\n'
            '      "career_stage": "<Emerging | Growing | Established>",\n'
            '      "future_demand": "<Very High | High | Moderate>",\n'
            '      "industry": "<industry name>",\n'
            '      "skills": ["<skill1>", "<skill2>"],\n'
            '      "sources": ["<url1>", "<url2>"]\n'
            "    }\n"
            "  ]\n"
            "}\n\n"
            f"Previous Response:\n{malformed_response}"
        )

        payload = {
            "model": self.model_name,
            "prompt": repair_prompt,
            "stream": False,
            "format": "json",
        }

        try:
            response_data = self._post_request(payload)
            return response_data.get("response", "").strip()
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

    def _parse_response(self, raw: dict) -> CareerTrendResponse:
        """
        Convert the parsed JSON dictionary into the CareerTrendResponse schema.
        """
        try:
            recommendations: list[CareerRecommendation] = []
            for path in raw.get("recommended_paths", []):
                # Defensive mapping/validation for CareerRecommendation constructor
                career_stage = str(path.get("career_stage", "Growing")).strip().title()
                if career_stage not in ("Emerging", "Growing", "Established"):
                    career_stage = "Growing"

                future_demand = str(path.get("future_demand", "High")).strip()
                # Handle title-casing but preserve "Very High"
                parts = [p.title() for p in future_demand.split()]
                future_demand = " ".join(parts)
                if future_demand not in ("Very High", "High", "Moderate"):
                    future_demand = "High"

                conf_raw = path.get("confidence", 80)
                if isinstance(conf_raw, str):
                    conf_raw = "".join(c for c in conf_raw if c.isdigit())
                try:
                    confidence = int(conf_raw) if conf_raw else 80
                except (ValueError, TypeError):
                    confidence = 80

                rec = CareerRecommendation(
                    career=path.get("career", ""),
                    category=path.get("category", ""),
                    confidence=confidence,
                    why_for_you=path.get("why_for_you", ""),
                    career_stage=career_stage,
                    future_demand=future_demand,
                    industry=path.get("industry", "Technology"),
                    skills=path.get("skills", []),
                    sources=path.get("sources", []),
                )
                recommendations.append(rec)

            # Sort by confidence descending
            recommendations.sort(key=lambda r: r.confidence, reverse=True)

            strategy = raw.get("strategy", "")
            if not strategy:
                strategy = "No overall strategy provided."

            return CareerTrendResponse(
                recommended_paths=recommendations,
                strategy=strategy,
                generated_at=datetime.now(tz=timezone.utc),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise LLMServiceError(
                f"Failed to parse LLM response dict into CareerTrendResponse object: {exc}. "
                f"Parsed JSON keys: {list(raw.keys()) if isinstance(raw, dict) else type(raw)}"
            ) from exc
