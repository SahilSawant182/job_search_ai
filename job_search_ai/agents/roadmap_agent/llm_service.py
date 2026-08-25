from __future__ import annotations

import json
import logging
import os
import urllib.request
import urllib.error
import requests
from openai import OpenAI, OpenAIError
from headroom import compress

from job_search_ai.services.settings_service import SettingsService

logger = logging.getLogger(__name__)

class LLMServiceError(Exception):
    """Raised when LLM call or response parsing fails."""
    pass

class LLMService:
    def __init__(self, model_name: str | None = None):
        settings = SettingsService.get()
        provider = (settings.llm_provider or "ollama").lower().strip()

        SUPPORTED_PROVIDERS = {"ollama", "omniroute"}
        if provider not in SUPPORTED_PROVIDERS:
            raise RuntimeError(
                f"Unsupported LLM_PROVIDER='{provider}'. "
                f"Supported values are: {', '.join(sorted(SUPPORTED_PROVIDERS))}."
            )

        self.provider = provider
        self.use_omniroute = provider == "omniroute"
        self.timeout = int(settings.llm_timeout_seconds or 180)
        if not self.use_omniroute:
            self.timeout = min(self.timeout, 120)
        self.retry_count = int(settings.retry_count or 1)

        if self.use_omniroute:
            api_key = os.getenv("OMNIROUTE_API_KEY")
            if not api_key:
                import frappe
                if frappe.local and getattr(frappe.local, "initialised", False):
                    api_key = frappe.conf.get("omniroute_api_key")
            if not api_key:
                raise RuntimeError("OMNIROUTE_API_KEY environment variable or omniroute_api_key in site_config.json is not configured.")
            base_url = settings.omniroute_base_url or "http://localhost:20128/v1"
            self.model_name = model_name or settings.omniroute_model or "roadmap-agent"
            self.client = OpenAI(base_url=base_url, api_key=api_key)
        else:
            self.model_name = model_name or settings.default_llm_model
            self.base_url = settings.ollama_endpoint
            self.client = None

    def call_agent(self, prompt: str) -> str:
        """Call the LLM with the roadmap prompt and retry logic."""
        # Headroom compression bypassed for speed optimization.
        compressed_prompt = prompt
        compressed_messages = [{"role": "user", "content": prompt}]

        # 2. Invoke provider with retry logic
        last_exc: Exception | None = None
        max_attempts = self.retry_count + 1

        for attempt in range(1, max_attempts + 1):
            try:
                if self.use_omniroute:
                    logger.info("Calling OmniRoute LLM (attempt %d/%d)", attempt, max_attempts)
                    response = self.client.chat.completions.create(
                        model=self.model_name,
                        messages=compressed_messages,
                        response_format={"type": "json_object"},
                        timeout=self.timeout
                    )
                    return response.choices[0].message.content or ""
                else:
                    logger.info("Calling Ollama LLM (attempt %d/%d)", attempt, max_attempts)
                    try:
                        payload = {
                            "model": self.model_name,
                            "prompt": compressed_prompt,
                            "stream": False,
                            "format": "json"
                        }
                        req = urllib.request.Request(
                            self.base_url,
                            data=json.dumps(payload).encode("utf-8"),
                            headers={"Content-Type": "application/json"},
                            method="POST"
                        )
                        with urllib.request.urlopen(req, timeout=self.timeout) as response:
                            if response.status != 200:
                                raise RuntimeError(f"Ollama API responded with HTTP status {response.status}")
                            body = response.read().decode("utf-8")
                            return json.loads(body).get("response", "").strip()
                    except Exception as ollama_err:
                        logger.warning("Ollama call failed on attempt %d: %s. Trying OmniRoute fallback...", attempt, ollama_err)
                        try:
                            import os
                            from openai import OpenAI
                            api_key = os.getenv("OMNIROUTE_API_KEY")
                            if not api_key:
                                import frappe
                                if frappe.local and getattr(frappe.local, "initialised", False):
                                    api_key = frappe.conf.get("omniroute_api_key")
                            
                            if api_key:
                                settings = SettingsService.get()
                                base_url = settings.omniroute_base_url or "http://localhost:20128/v1"
                                model_name = settings.omniroute_model or "roadmap-agent"
                                fallback_client = OpenAI(base_url=base_url, api_key=api_key)
                                response = fallback_client.chat.completions.create(
                                    model=model_name,
                                    messages=compressed_messages,
                                    response_format={"type": "json_object"},
                                    timeout=self.timeout
                                )
                                logger.info("OmniRoute fallback call succeeded.")
                                return response.choices[0].message.content or ""
                            else:
                                raise RuntimeError("OMNIROUTE_API_KEY not found for fallback.")
                        except Exception as fallback_exc:
                            logger.warning("OmniRoute fallback also failed: %s", fallback_exc)
                            raise ollama_err
            except Exception as exc:
                last_exc = exc
                logger.warning("LLM call attempt %d failed: %s", attempt, exc)

        raise LLMServiceError(f"Roadmap LLM call failed after {max_attempts} attempts: {last_exc}")
