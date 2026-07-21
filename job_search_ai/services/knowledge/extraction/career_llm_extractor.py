# -*- coding: utf-8 -*-
"""
CareerLLMExtractor — extracts structured career profiles from raw search text
using a lightweight LLM call.

WHY THIS EXISTS
---------------
The previous heuristic extractor (CareerFactExtractor._extract_career_titles)
took the first line of every paragraph as a career title candidate.  This caused
it to store blog headings ("Top Companies Hiring"), table headers ("Salary Range"),
and numbered steps ("Trend 3 Serverless Computing") as career names — producing
a knowledge base with ~10% accuracy.

An LLM call with a strict JSON schema is the only reliable way to:
  1. Distinguish "Backend Developer" from "Top Companies Hiring" in raw HTML prose.
  2. Extract structured required_skills, preferred_skills, suitable_degrees,
     suitable_branches, suitable_years, and future_demand in one pass.

DESIGN DECISIONS
----------------
- Uses the same Ollama endpoint as LLMService (no new dependency).
- Produces at most MAX_CAREERS career profiles per call (default 3).
- Input text is truncated to MAX_INPUT_CHARS to stay within the model's context.
- Returns an empty list on any failure — callers must handle this gracefully.
- Does NOT call Tavily.  Pure text → structured JSON transform.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

# Maximum characters of search text fed to the LLM (keep prompt small).
# qwen2.5:1.5b generation time scales with input length — 2500 chars gives
# enough context to extract 3 career profiles while keeping latency low (~5-8s).
MAX_INPUT_CHARS = 2_500

# Maximum career profiles to extract per call.
MAX_CAREERS = 3

# Hard timeout for the extraction LLM call (seconds).
_TIMEOUT = 45


def _call_ollama(prompt: str, endpoint: str, model: str) -> str:
    """Send prompt to Ollama and return raw response text."""
    payload = {
        "model":  model,
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
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        body = resp.read().decode("utf-8")
        return json.loads(body).get("response", "").strip()


def _call_openai_compat(prompt: str, base_url: str, api_key: str, model: str) -> str:
    """Send prompt via OpenAI-compatible API (OmniRoute) and return raw response."""
    from openai import OpenAI
    client = OpenAI(base_url=base_url, api_key=api_key)
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        timeout=_TIMEOUT,
    )
    return resp.choices[0].message.content or ""


def _clean_json(text: str) -> str:
    """Strip markdown fences if the model wrapped the output."""
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


def _build_prompt(career_focus: str, search_text: str) -> str:
    """
    Build the extraction prompt.

    The prompt is deliberately minimal to keep token usage low.
    The LLM is told EXACTLY what to output and EXACTLY what to ignore.
    """
    truncated = search_text[:MAX_INPUT_CHARS]

    # Dynamically select example based on whether the career focus is technical
    focus_lower = career_focus.lower()
    is_tech = any(kw in focus_lower for kw in ["machine", "web", "dev", "program", "code", "software", "data", "engineer", "tech", "computer", "ml", "ai"])

    if is_tech:
        deg_eg = '["B.Tech", "B.Sc", "MCA"]'
        branch_eg = '["Computer Science", "Information Technology"]'
    else:
        deg_eg = '["MBA", "BBA", "B.Com"]'
        branch_eg = '["Marketing", "Business Administration"]'

    return (
        "You are a career data extractor.  Your ONLY job is to read the text below and "
        f"extract up to {MAX_CAREERS} real, hireable job roles related to: {career_focus!r}.\n\n"
        "Rules:\n"
        "1. ONLY extract actual job titles that appear in job postings "
        "(e.g. 'Digital Marketing Manager', 'Product Manager', 'SEO Specialist').\n"
        "2. NEVER extract: company names, article headings, section headers, salary ranges, "
        "skill lists, numbered steps, academic subjects, tool names, or navigation text.\n"
        "3. For each job role, determine:\n"
        f"   - required_skills: 3-8 must-have technical skills for this role.\n"
        f"   - preferred_skills: 2-5 nice-to-have or advanced skills.\n"
        f"   - suitable_degrees: list of degree types (e.g. {deg_eg}).\n"
        f"   - suitable_branches: list of academic branches (e.g. {branch_eg}).\n"
        "   - suitable_years: list of academic years as integers, e.g. [3, 4] for final-year students.\n"
        "   - aliases: list of 2-4 alternative title variants/synonyms (e.g. ['Frontend Engineer', 'UI Developer']).\n"
        "   - future_demand: one of 'Very High', 'High', 'Medium', 'Low'.\n"
        "   - confidence: integer 0-100 reflecting how well the role matches the search topic.\n"
        "4. If you cannot find any real job roles, return {\"careers\": []}.\n"
        "5. Return ONLY valid JSON. No explanations. No markdown.\n\n"
        "Output schema:\n"
        "{\n"
        '  "careers": [\n'
        "    {\n"
        '      "career_name": "exact job title",\n'
        '      "aliases": ["Frontend Engineer", "UI Developer"],\n'
        '      "career_name": "exact job title",\n'
        '      "aliases": ["Frontend Engineer", "UI Developer"],\n'
        '      "required_skills": ["JavaScript", "HTML"],\n'
        '      "preferred_skills": ["React"],\n'
        f'      "suitable_degrees": {deg_eg},\n'
        f'      "suitable_branches": {branch_eg},\n'
        '      "suitable_years": [3, 4],\n'
        '      "future_demand": "High",\n'
        '      "confidence": 85\n'
        "    }\n"
        "  ]\n"
        "}\n\n"
        "--- TEXT TO ANALYSE ---\n"
        f"{truncated}\n"
        "--- END TEXT ---\n\n"
        "Return ONLY the JSON object:"
    )


def _validate_career(raw: dict) -> dict | None:
    """
    Validate and normalise a single career dict from the LLM output.
    Returns None if the entry is not a valid career profile.
    """
    career_name = str(raw.get("career_name") or "").strip()
    if not career_name or len(career_name) < 3 or len(career_name) > 80:
        return None

    # Reject obvious non-career titles (very short sanity check — full
    # canonicalization is done downstream by CareerCanonicalizer)
    lower = career_name.lower()
    junk_signals = [
        "top ", "best ", "how to", "guide", "salary", "interview", "course",
        "tutorial", "roadmap", "step ", "click", "sign up", "apply now",
        "skills for", "tools for", "companies", "hiring", "trends", "overview",
    ]
    if any(junk in lower for junk in junk_signals):
        logger.info("CareerLLMExtractor: rejected junk title %r", career_name)
        return None

    # Word count sanity — job titles are 1-5 words
    if len(career_name.split()) > 6:
        logger.info("CareerLLMExtractor: rejected over-long title %r", career_name)
        return None

    DUMMY_SKILL_RE = re.compile(r"^(skill\d+|unknown|n/a|placeholder|none)$", re.IGNORECASE)

    def _to_str_list(val, default=None) -> list[str]:
        items = []
        if isinstance(val, list):
            items = [str(v).strip() for v in val if str(v).strip()]
        elif isinstance(val, str) and val.strip():
            items = [v.strip() for v in re.split(r"[,;]", val) if v.strip()]
        else:
            items = default or []
        return [i for i in items if not DUMMY_SKILL_RE.match(i)]

    def _to_int_list(val) -> list[int]:
        if isinstance(val, list):
            result = []
            for v in val:
                try:
                    result.append(int(v))
                except (TypeError, ValueError):
                    pass
            return result
        return []

    aliases          = _to_str_list(raw.get("aliases"))
    required_skills  = _to_str_list(raw.get("required_skills"))
    preferred_skills = _to_str_list(raw.get("preferred_skills"))
    suitable_degrees = _to_str_list(raw.get("suitable_degrees"))
    suitable_branches = _to_str_list(raw.get("suitable_branches"))
    suitable_years   = _to_int_list(raw.get("suitable_years"))
    future_demand    = str(raw.get("future_demand") or "High").strip()
    confidence       = int(raw.get("confidence") or 70)

    # Normalise demand to allowed values
    demand_map = {
        "very high": "Very High",
        "high":      "High",
        "medium":    "Medium",
        "moderate":  "Medium",
        "low":       "Low",
    }
    future_demand = demand_map.get(future_demand.lower(), "High")

    # Require at least one required skill — otherwise this is not usable
    if not required_skills:
        logger.info(
            "CareerLLMExtractor: rejected %r — no required_skills extracted", career_name
        )
        return None

    return {
        "career_name":       career_name,
        "aliases":           aliases,
        "required_skills":   required_skills,
        "preferred_skills":  preferred_skills,
        "suitable_degrees":  suitable_degrees,
        "suitable_branches": suitable_branches,
        "suitable_years":    suitable_years,
        "future_demand":     future_demand,
        "confidence":        max(0, min(100, confidence)),
    }


class CareerLLMExtractor:
    """
    Extracts up to MAX_CAREERS structured career profiles from raw search text
    using a lightweight LLM call.

    Usage
    -----
    ::
        profiles = CareerLLMExtractor.extract(
            search_text="...",
            career_focus="Digital Marketing",
        )
        # profiles = [
        #   {
        #     "career_name": "Digital Marketing Manager",
        #     "required_skills": ["SEO", "Google Analytics", ...],
        #     "preferred_skills": [...],
        #     "suitable_degrees": ["MBA", "BBA"],
        #     "suitable_branches": ["Marketing"],
        #     "suitable_years": [3, 4],
        #     "future_demand": "High",
        #     "confidence": 82,
        #   },
        #   ...
        # ]
    """

    @staticmethod
    def extract(
        search_text: str,
        career_focus: str,
        endpoint: str | None = None,
        model: str | None = None,
    ) -> list[dict]:
        """
        Extract structured career profiles from search text.

        Parameters
        ----------
        search_text  : Concatenated cleaned text from Tavily search results.
        career_focus : The career area being searched (used to focus the LLM).
        endpoint     : Ollama endpoint URL (read from SettingsService if None).
        model        : LLM model name (read from SettingsService if None).

        Returns
        -------
        List of validated career dicts.  Empty list on any failure.
        """
        if not search_text or not search_text.strip():
            logger.warning("CareerLLMExtractor: empty search_text — returning []")
            return []

        # Load settings
        from job_search_ai.services.settings_service import SettingsService
        settings = SettingsService.get()
        provider = (settings.llm_provider or "ollama").lower().strip()

        if endpoint is None:
            endpoint = settings.ollama_endpoint
        if model is None:
            if provider == "omniroute":
                model = settings.omniroute_model or "career-agent"
            else:
                model = settings.default_llm_model

        prompt = _build_prompt(career_focus, search_text)

        try:
            if provider == "omniroute":
                import os
                api_key = os.getenv("OMNIROUTE_API_KEY")
                if not api_key:
                    import frappe
                    if frappe.local and getattr(frappe.local, "initialised", False):
                        api_key = frappe.conf.get("omniroute_api_key")
                base_url = settings.omniroute_base_url or "http://localhost:20128/v1"
                raw_text = _call_openai_compat(prompt, base_url, api_key or "", model)
            else:
                raw_text = _call_ollama(prompt, endpoint, model)
        except Exception as exc:
            logger.warning(
                "CareerLLMExtractor: LLM call failed (%s) — returning []", exc
            )
            return []

        raw_text = _clean_json(raw_text)
        if not raw_text:
            logger.warning("CareerLLMExtractor: empty LLM response — returning []")
            return []

        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError:
            # Try to find the JSON object in the response
            match = re.search(r'\{.*\}', raw_text, re.DOTALL)
            if match:
                try:
                    parsed = json.loads(match.group(0))
                except json.JSONDecodeError:
                    logger.warning(
                        "CareerLLMExtractor: failed to parse JSON — %r", raw_text[:200]
                    )
                    return []
            else:
                logger.warning(
                    "CareerLLMExtractor: no JSON found in response — %r", raw_text[:200]
                )
                return []

        raw_careers = parsed.get("careers", [])
        if not isinstance(raw_careers, list):
            logger.warning(
                "CareerLLMExtractor: 'careers' key is not a list — got %r", type(raw_careers)
            )
            return []

        validated = []
        for raw in raw_careers[:MAX_CAREERS]:
            profile = _validate_career(raw)
            if profile:
                validated.append(profile)

        logger.info(
            "CareerLLMExtractor: career_focus=%r  raw=%d  validated=%d",
            career_focus, len(raw_careers), len(validated),
        )
        return validated
