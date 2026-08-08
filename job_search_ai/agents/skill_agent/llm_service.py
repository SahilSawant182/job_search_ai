"""
LLM client for direct skill generation.

No Tavily / web search involved — the model generates the three skill
tiers straight from its own training knowledge, in a single call.
"""

from __future__ import annotations
from headroom import compress
import frappe
import json
import logging
import tiktoken
import requests
_enc = tiktoken.get_encoding("cl100k_base")
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

    def _build_prompt(self, role, seniority):
        return f"""
        ROLE={role}
        LEVEL={seniority or "Junior"}

        TASK=Generate industry-specific competency hierarchy.
        Each skill category must be a flat list of strings (exact skill names only). Do NOT output objects or dicts.

        ROLE-SPECIFICITY RULE:
        Skills must be highly specific and tailormade to {role}. Do NOT output generic software engineering terms like "Database Management", "API Development", or "Version Control" if more specific tool-specific skills are relevant.
        For example:
        - Instead of "Database Management", output "MariaDB" or "PostgreSQL" or "Frappe ORM".
        - Instead of "API Development", output "Frappe REST API" or "Webhooks".
        - Instead of "General Programming", output "Python", "JavaScript", "Jinja templating".
        - For emerging, output actual emerging tech relevant to the role (e.g., "AI-assisted ERP automation", "LLM integration with Frappe", "AI agents for ERP workflows").

        RULES:
        - Each skill list must contain only string values (e.g. ["Python", "JavaScript"]). Do NOT include details like descriptions, counts, or objects.
        - single_path
        - profession_only
        - ordered
        - modern
        - atomic_skills
        - canonical_names
        - no_duplicates
        - json_only

        TARGET COUNTS:
        - foundation_skills: 5 to 8 skills (strings)
        - core_domain_skills: 10 to 15 skills (strings)
        - industry_skills: 5 to 10 skills (strings)
        - emerging_skills: 3 to 6 skills (strings)

        EXPECTED OUTPUT FORMAT (JSON ONLY):
        {{
          "role": "{role}",
          "foundation_skills": [
            "Skill Name 1",
            "Skill Name 2"
          ],
          "core_domain_skills": [
            "Skill Name 1"
          ],
          "industry_skills": [
            "Skill Name 1"
          ],
          "emerging_skills": [
            "Skill Name 1"
          ]
        }}
        """

    # def _call(self, prompt: str) -> str:
    #     result = compress(
    #         messages=[{"role": "user", "content": prompt}],
    #         model=self.model_name,
    #     )
    #     compressed_messages = result.messages
    #     compressed_prompt = compressed_messages[0]["content"]

    #     logger.info(
    #         "headroom: saved %d tokens (%.0f%% reduction)",
    #         result.tokens_saved, result.compression_ratio * 100,
    #     )

    #     if self.provider == "omniroute":
    #         resp = requests.post(
    #             f"{self.base_url.rstrip('/')}/chat/completions",
    #             json={
    #                 "model": self.model_name,
    #                 "messages": compressed_messages,
    #                 "temperature": 0.2,
    #             },
    #             timeout=self.timeout,
    #         )

    def _call(self, prompt: str) -> str:
        result = compress(
            messages=[{"role": "user", "content": prompt}],
            model=self.model_name,
        )
        compressed_messages = result.messages
        logger.info(
            "headroom: saved %d tokens (%.0f%% reduction)",
            result.tokens_saved, result.compression_ratio * 100,
        )
        frappe.logger("headroom").info(
    "saved %d tokens (%.0f%% reduction)",
    result.tokens_saved, result.compression_ratio * 100,
)

        if self.provider == "omniroute":
            resp = requests.post(
                f"{self.base_url.rstrip('/')}/chat/completions",
                json={
                    "model": self.model_name,
                    "messages": compressed_messages,
                    "temperature": 0.2,
                },
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]

        # Ollama /api/generate wants ONE flat string. compress() may return
        # multiple messages (e.g. a stabilized prefix + dynamic tail) or a
        # message with content=None — flatten and filter rather than
        # assuming messages[0] holds everything.
        compressed_prompt = "\n".join(
            m["content"] for m in compressed_messages if m.get("content")
        )
        if not compressed_prompt.strip():
            logger.warning("headroom: compression returned no usable content — falling back to original prompt")
            compressed_prompt = prompt

        resp = requests.post(
            self.base_url,
            json={
                "model": self.model_name,
                "prompt": compressed_prompt,
                "stream": False,
                "options": {"temperature": 0.2},
            },
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("response", "")
        
    # def _call(self, prompt: str) -> str:
    #     if self.provider == "omniroute":
    #         resp = requests.post(
    #             f"{self.base_url.rstrip('/')}/chat/completions",
    #             json={
    #                 "model": self.model_name,
    #                 "messages": [{"role": "user", "content": prompt}],
    #                 "temperature": 0.2,
    #             },
    #             timeout=self.timeout,
    #         )
    #         resp.raise_for_status()    
    #         data = resp.json()
    #         return data["choices"][0]["message"]["content"]
 
    #     resp = requests.post(
    #         self.base_url,
    #         json={
    #             "model": self.model_name,
    #             "prompt": prompt,
    #             "stream": False,
    #             "options": {"temperature": 0.2},
    #         },
    #         timeout=self.timeout,
    #     )
    #     resp.raise_for_status()
    #     data = resp.json()
    #     return data.get("response", "")


    def _normalize_skill_list(self, val) -> list[str]:
        if not isinstance(val, list):
            return []
        result = []
        for item in val:
            if isinstance(item, str):
                result.append(item.strip())
            elif isinstance(item, dict):
                name = item.get("name") or item.get("skill") or item.get("title")
                if name:
                    result.append(str(name).strip())
        return result

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
            "foundation_skills": self._normalize_skill_list(payload.get("foundation_skills")),
            "core_domain_skills": self._normalize_skill_list(payload.get("core_domain_skills")),
            "industry_skills": self._normalize_skill_list(payload.get("industry_skills")),
            "emerging_skills": self._normalize_skill_list(payload.get("emerging_skills")),
        }
     
        # Cross-tier deduplication after canonicalization:
        # A skill that appeared in an earlier tier is removed from later tiers.
        # Comparison is done on a normalised key (lowercase, strip spaces/hyphens)
        # so that "Git", "git", and "Git Version Control" (already stripped to "Git")
        # all collapse to the same key.
        seen_keys: set[str] = set()
        for tier_field in ("foundation_skills", "core_domain_skills", "industry_skills", "emerging_skills"):
            deduped: list[str] = []
            for s in tiers[tier_field]:
                key = s.strip().lower().replace(" ", "").replace("-", "").replace("_", "")
                if key not in seen_keys:
                    seen_keys.add(key)
                    deduped.append(s)
            tiers[tier_field] = deduped
        return tiers
     
