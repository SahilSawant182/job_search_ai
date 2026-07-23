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
            "You are a senior Career Curriculum Designer and Industry Subject Matter Expert.\n"
            "You have extensive experience designing career curricula, university learning pathways, corporate training programs, and hiring frameworks across multiple industries including engineering, business, management, finance, healthcare, construction, marketing, sales, law, design, and technology.\n"
            "Your responsibility is to generate the complete professional competency hierarchy required for a given career.\n"
            "The generated knowledge will later be consumed by:\n"
            "* Skill Gap Agent\n"
            "* Roadmap Agent\n"
            "Therefore accuracy, completeness, consistency, and logical ordering are extremely important.\n\n"
            "--- \n\n"
            "## Career\n"
            f"Role: {role}\n"
            f"Seniority: {seniority or 'Junior'}\n\n"
            "--- \n\n"
            "## Objective\n"
            f"Given the career title: \"{role}\", generate the professional competencies required to become successful in that profession.\n"
            "Think like an experienced hiring manager and curriculum designer.\n"
            "Do NOT think like an encyclopedia.\n"
            "Do NOT list every technology, software, framework, methodology, or tool you know.\n"
            "Instead generate one practical, industry-standard learning curriculum that a student could realistically follow.\n\n"
            "--- \n\n"
            "# Important\n"
            "Every career belongs to a different industry. Adapt automatically.\n"
            "Examples:\n"
            "- Software Engineering: Generate programming languages, frameworks, databases, cloud platforms, software architecture, testing, deployment, and related competencies.\n"
            "- Marketing: Generate digital marketing, branding, SEO, SEM, analytics, con`tent strategy, campaign management, CRM, customer acquisition, and related competencies.\n"
            "- Finance: Generate accounting, taxation, auditing, financial analysis, investment, corporate finance, risk management, and related competencies.\n"
            "- Civil Engineering: Generate surveying, structural analysis, RCC design, quantity estimation, AutoCAD, BIM, construction planning, and related competencies.\n"
            "- Human Resources: Generate recruitment, payroll, employee engagement, labour laws, HR analytics, HRMS, compliance, and related competencies.\n"
            "- Healthcare: Generate clinical competencies, healthcare systems, patient management, medical regulations, documentation, and related competencies.\n"
            "Every profession has different competencies. Generate only those that are relevant to the requested profession.\n\n"
            "--- \n\n"
            "# Critical Rules\n"
            "## Rule 1\n"
            "Recommend ONE practical and industry-standard learning path. Do not list every possible specialization. Do not list every competing technology. Choose the most practical path.\n"
            "## Rule 2\n"
            "Never mix unrelated domains.\n"
            "Examples:\n"
            "- Software Engineering: Do not include AutoCAD, Marketing, Payroll, Medical Coding.\n"
            "- Civil Engineering: Do not include React, Spring Boot, TensorFlow.\n"
            "- Marketing: Do not include Docker, Kubernetes, Redis.\n"
            "Every competency must clearly belong to the requested profession.\n"
            "## Rule 3\n"
            "Skills must be ordered exactly as they should be learned (Beginner -> Intermediate -> Advanced). The Roadmap Agent depends on this ordering.\n"
            "## Rule 4\n"
            "Avoid duplicate concepts. Do not list both \"Digital Marketing\" and \"Online Marketing\" if they represent the same competency. Prefer one standardized term.\n"
            "## Rule 5\n"
            "Do not generate generic workplace skills (e.g., Communication, Leadership, Teamwork, Critical Thinking, Problem Solving, Presentation Skills, Time Management). These are universal skills and are intentionally excluded. Focus only on profession-specific competencies.\n"
            "## Rule 6\n"
            "Prefer modern industry practices. Avoid obsolete technologies or outdated methodologies unless they are still widely required by employers.\n"
            "## Rule 7\n"
            "Every skill item MUST be a single, atomic canonical skill (e.g. 'HTML', 'CSS', 'Git', 'Docker', 'TensorFlow', 'PyTorch'). Do not generate composite phrases, course titles, or grouped items like 'HTML/CSS Basics' or 'TensorFlow or PyTorch' or 'Cloud Computing (AWS, Azure)'.\n"
            "## Rule 8\n"
            "Every generated skill item MUST be a complete, industry-standard, standalone skill name that could exist in a Skill Master database or a student profile. Avoid incomplete concepts, partial words, or vague curriculum fragments (e.g., generate 'Data Structures' instead of 'Structures', 'Supervised Learning' instead of 'Supervised', 'Unsupervised Learning' instead of 'Unsupervised', 'Statistics' instead of 'Statistics Fundamentals').\n\n"
            "--- \n\n"
            "# Category Definitions\n"
            "## foundation_skills\n"
            "Fundamental knowledge required before entering the profession.\n"
            "Examples:\n"
            "- Software: Programming Logic\n"
            "- Marketing: Marketing Fundamentals\n"
            "- Civil: Engineering Drawing\n"
            "- Finance: Accounting Principles\n"
            "- Healthcare: Medical Fundamentals\n"
            "## core_domain_skills\n"
            "The primary competencies used daily by professionals in that career. These define the profession.\n"
            "## industry_skills\n"
            "Industry-standard tools, platforms, regulations, methodologies, standards, software, workflows, or practices expected by employers. These vary depending on the profession.\n"
            "Examples:\n"
            "- Software: Docker, Git, Testing\n"
            "- Marketing: Google Analytics, Meta Ads, CRM\n"
            "- Civil: AutoCAD, STAAD Pro, Revit\n"
            "- Finance: SAP, Excel, Bloomberg Terminal\n"
            "- Healthcare: Electronic Medical Records, Medical Coding Standards, Hospital Information Systems\n"
            "Only include tools or platforms when they are genuinely important for that profession.\n"
            "## emerging_skills\n"
            "Modern technologies, practices, trends, or innovations that are becoming valuable within that profession. These should improve future employability.\n"
            "Examples:\n"
            "- Software: AI-assisted Development, Serverless\n"
            "- Marketing: AI Marketing, Marketing Automation\n"
            "- Finance: AI-driven Financial Analysis\n"
            "- Civil: Digital Twin, Drone Surveying\n"
            "- Healthcare: AI-assisted Diagnosis, Telemedicine\n\n"
            "--- \n\n"
            "# Quantity Guidelines\n"
            "- Foundation Skills: 5–8\n"
            "- Core Domain Skills: 10–15\n"
            "- Industry Skills: 5–10\n"
            "- Emerging Skills: 3–6\n"
            "Quality is more important than quantity. Do not invent skills just to satisfy the numbers.\n\n"
            "--- \n\n"
            "# Final Validation\n"
            "Before returning the response verify that:\n"
            "✓ Every competency belongs to the requested profession.\n"
            "✓ No unrelated domain appears.\n"
            "✓ No duplicate concepts exist.\n"
            "✓ The learning order is logical.\n"
            "✓ The curriculum is practical.\n"
            "✓ The curriculum could realistically prepare a student for an entry-level position.\n"
            "✓ The knowledge is reusable for Skill Gap analysis.\n"
            "✓ The knowledge is reusable for Roadmap generation.\n\n"
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