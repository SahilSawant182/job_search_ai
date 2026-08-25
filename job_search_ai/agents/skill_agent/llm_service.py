import json
import logging
import requests
import frappe
from job_search_ai.services.settings_service import SettingsService

logger = logging.getLogger(__name__)

class LLMServiceError(Exception):
    pass

class LLMService:    

    def __init__(self):
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

    def generate_skills(self, role: str, seniority: str | None = None, feedback: str | None = None) -> dict:
        """Returns a dict containing all 8 new skill profile fields."""
        
        # Load guidance skills from Career Knowledge database
        guidance_skills = []
        try:
            from job_search_ai.agents.skill_agent.doctype_writer import _resolve_job_profile
            ck_name = _resolve_job_profile(role)
            if ck_name:
                skills_list = frappe.db.sql(
                    "SELECT skill_name FROM `tabCareer Knowledge Skill` WHERE parent = %s",
                    (ck_name,),
                    as_dict=True
                )
                guidance_skills = [s["skill_name"] for s in skills_list if s.get("skill_name")]
        except Exception as e:
            logger.warning("LLMService: Failed to fetch guidance skills: %s", e)

        prompt = self._build_prompt(role, seniority, feedback, guidance_skills)

        last_exc: Exception | None = None
        for attempt in range(self.retry_count + 1):
            try:
                raw_text = self._call(prompt)
                return self._parse(raw_text)
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                logger.warning("LLMService.generate_skills attempt %d failed: %s", attempt + 1, exc)
        raise LLMServiceError(f"Skill generation failed after retries: {last_exc}") from last_exc

    def _build_prompt(self, role, seniority, feedback=None, guidance_skills=None):
        if not guidance_skills:
            try:
                from job_search_ai.agents.skill_agent.doctype_writer import _resolve_job_profile
                ck_name = _resolve_job_profile(role)
                if ck_name:
                    skills_list = frappe.db.sql(
                        "SELECT skill_name FROM `tabCareer Knowledge Skill` WHERE parent = %s",
                        (ck_name,),
                        as_dict=True
                    )
                    guidance_skills = [s["skill_name"] for s in skills_list if s.get("skill_name")]
            except Exception as e:
                logger.warning("LLMService: failed to query Career Knowledge skills for %r: %s", role, e)

        career_knowledge_section = ""
        if guidance_skills:
            career_knowledge_section = (
                f"CAREER KNOWLEDGE REQUIREMENTS:\n"
                f"Based on our career database, the following core skills are required for \"{role}\" and MUST be included in your output:\n"
                f"- {', '.join(guidance_skills)}\n"
            )

        cse_keywords = [
            "web", "developer", "software", "programmer", "data", "cloud", "ai", "ml", 
            "cyber", "network", "system", "computer", "devops", "qa", "test", "frontend", 
            "backend", "full-stack", "fullstack", "blockchain", "coding", "coder"
        ]
        is_cse = any(kw in str(role).lower() for kw in cse_keywords)

        if is_cse:
            tier_definitions = """- foundation_skills: The absolute baseline prerequisites, core sciences, primary programming languages, basic design/coding tools, and foundational theories required to start learning this field. (e.g.: "HTML", "CSS", "JavaScript", "Git"). DO NOT put advanced frameworks, libraries, databases, or cloud technologies here.
        - core_domain_skills: The primary practical tools, frameworks, core subject-matter disciplines, and technologies used daily by professionals in this specific role. (e.g.: "React", "Redux", "TypeScript").
        - industry_skills: Professional methodologies, cloud platforms, advanced deployment/execution tools, systems architecture, compliance standards, and production-grade practices. (e.g.: "RESTful API Integration", "Responsive Web Design", "Web Performance Optimization").
        - emerging_skills: Cutting-edge innovations, next-generation paradigms, AI integrations, or new-wave tools shaping the future of this profession. (e.g.: "AI-assisted development")."""
            few_shot_example = """If ROLE="Frontend Developer", a correct response would be:
        {
          "role": "Frontend Developer",
          "foundation_skills": [
            "HTML",
            "CSS",
            "JavaScript",
            "Git"
          ],
          "core_domain_skills": [
            "React",
            "Redux",
            "TypeScript"
          ],
          "industry_skills": [
            "RESTful API Integration",
            "Responsive Web Design",
            "Web Performance Optimization"
          ],
          "emerging_skills": [
            "AI-assisted development"
          ]
        }"""
        else:
            tier_definitions = """- foundation_skills: The absolute baseline prerequisites, core sciences, primary design/CAD tools, and foundational theories required to start learning this field. (e.g.: "Engineering Drawing", "Structural Mechanics", "Engineering Mathematics"). DO NOT put advanced frameworks, structural design suites, or professional simulation tools here.
        - core_domain_skills: The primary practical tools, software suites, core subject-matter disciplines, and technologies used daily by professionals in this specific role. (e.g.: "ETABS", "Reinforced Concrete Design", "Foundation Engineering").
        - industry_skills: Professional methodologies, compliance standards, advanced simulation/design tools, project management, and production-grade field practices. (e.g.: "BIM (Building Information Modeling)", "Structural Design Standards").
        - emerging_skills: Cutting-edge innovations, next-generation paradigms, AI integrations, or new-wave technologies shaping the future of this profession. (e.g.: "3D Concrete Printing")."""
            few_shot_example = """If ROLE="Civil Engineer (Structural)", a correct response would be:
        {
          "role": "Civil Engineer (Structural)",
          "foundation_skills": [
            "Engineering Drawing",
            "Structural Mechanics",
            "Engineering Mathematics"
          ],
          "core_domain_skills": [
            "ETABS",
            "Reinforced Concrete Design",
            "Foundation Engineering"
          ],
          "industry_skills": [
            "BIM (Building Information Modeling)",
            "Structural Design Standards"
          ],
          "emerging_skills": [
            "3D Concrete Printing"
          ]
        }"""

        prompt_str = f"""
        ROLE={role}
        LEVEL={seniority or "Junior"}

        {career_knowledge_section}

        TASK=Generate the canonical competency profile for {role}.
        This output becomes canonical reusable knowledge for this career. Answer: "What is the minimum competency set required to perform this career/role effectively?"
        Generate a stable, role-specific competency profile, not a creative list of technologies. Prefer established industry-standard skills over speculative tools.

        MUST-TO-HAVE ONLY RULE:
        Only generate the absolute minimum must-to-have skills that are essential to perform this job. Do NOT list nice-to-have, auxiliary, or generic skills. For example, if the role is a Frontend Developer, do NOT output 'Docker', 'Kubernetes', or general DevOps/backend tools. The skills generated must be strictly focused on the core domain of {role}.

        NO STUDENT CONTEXT RULE:
        Do not customize the required skill profile based on an individual student's skills. This profile represents the general competency requirements of the career and must remain reusable across students.

        CANONICAL NAMING RULE:
        Do not create multiple names for the same competency. Use one canonical industry name. Do not create variants such as "Python Programming", "Python Language", and "Python Development" when they represent the same competency. Use one canonical skill name per concept.

        ATOMIC SKILL RULE:
        Every skill must be atomic, independently learnable or assessable, and specific to the requested career.
        Do not use vague skills such as "Management", "Development", "Integration", "Technology", "Practices", "Systems", "Tools", "Knowledge", or "Cloud" unless the term itself is a recognized standalone competency for the role.

        ROLE-SPECIFICITY RULE:
        Skills must be highly specific and tailored to {role}. Do NOT output generic terms when more specific tool-specific skills are relevant.
        - Instead of "Database Management" → "PostgreSQL" or "MongoDB" or "MySQL"
        - Instead of "API Development" → "RESTful APIs" or "GraphQL" or "Webhooks"
        - Instead of "General Programming" → "TypeScript" or "Python" or "JavaScript"
        - Instead of "Cloud" → "AWS" or "GCP" or "Azure"
        - Instead of "Monitoring" → "Prometheus" or "Grafana" or "Datadog"
        - Instead of "Automation" → "Terraform" or "Ansible" or "GitHub Actions"
        - For emerging, output actual next-gen tech relevant to the role (e.g., "AI-assisted development", "WebAssembly (Wasm)", "Edge Computing")

        ONE-TIER RULE:
        Each competency must belong to exactly one tier. Do not place equivalent skills or aliases in multiple tiers.
        Example of what NOT to do: Foundation: ["Git"] + Core: ["Version Control"] — these represent the same concept.

        NO FRONTEND COPY RULE:
        Do NOT copy foundation skills or core skills from the Frontend Developer example if the target ROLE is not Frontend or Full Stack.
        - For Backend Developer: Foundation must not contain HTML, CSS, JavaScript. It should contain backend foundation skills like Python, SQL, Git.
        - For DevOps Engineer: Foundation must not contain HTML, CSS, JavaScript. It should contain DevOps foundation skills like Git, Linux Command Line, Networking.
        - For AI Engineer: Foundation must not contain HTML, CSS, JavaScript. It should contain AI foundation skills like Python, Linear Algebra, Statistics, Git.
        - For Frappe Developer: Foundation must not contain HTML, CSS, JavaScript. It should contain Frappe foundation skills like Python, SQL, Git.

        NO VAGUE OR CLONE SKILLS:
        - NEVER generate vague/generic skills like "Systems", "Database Management", "API Development", or "Cloud". Be specific (e.g. "PostgreSQL", "RESTful APIs", "AWS").
        - NEVER generate duplicate/overlapping concepts (e.g., do NOT output both "WebAssembly" and "Wasm" in the same profile).

        TIER DEFINITIONS:
        {tier_definitions}

        MANDATORY VS OPTIONAL TIERS:
        - foundation_skills: Mandatory baseline (required for the role).
        - core_domain_skills: Mandatory domain competency (required for the role).
        - industry_skills: Optional/Specialized/Advanced (useful in production but not baseline).
        - emerging_skills: Optional/Future-facing (next-gen tech, not mandatory to get the job).

        RULES:
        - Each skill list must contain only string values (e.g. ["Python", "JavaScript"]). Do NOT include descriptions, counts, or objects.
        - single_path
        - profession_only
        - ordered
        - modern
        - atomic_skills
        - canonical_names
        - no_duplicates
        - json_only

        TARGET COUNTS:
        - foundation_skills: 3 to 6 skills (strings)
        - core_domain_skills: 4 to 8 skills (strings)
        - industry_skills: 2 to 5 skills (strings)
        - emerging_skills: 0 to 3 skills (strings)

        EXAMPLE:
        {few_shot_example}

        EXPECTED OUTPUT FORMAT (JSON ONLY):
        {{
          "role": "{role}",
          "foundation_skills": [
            "Skill Name 1",
            "Skill Name 2",
            "Skill Name 3"
          ],
          "core_domain_skills": [
            "Skill Name 1",
            "Skill Name 2",
            "Skill Name 3",
            "Skill Name 4"
          ],
          "industry_skills": [
            "Skill Name 1",
            "Skill Name 2"
          ],
          "emerging_skills": [
            "Skill Name 1"
          ]
        }}
        """

        if guidance_skills:
            prompt_str = prompt_str.strip() + f"\n\nREQUIRED BASELINE COMPETENCIES:\nThe career knowledge base indicates that a developer in this field MUST demonstrate proficiency in these skills. Make sure these (or highly similar canonical equivalents) are included in your output:\n{', '.join(guidance_skills)}"

        if feedback:
            prompt_str = prompt_str.strip() + f"\n\nCRITICAL FEEDBACK FROM PREVIOUS ATTEMPT:\nThe previous attempt was REJECTED by the career validator with the following error:\n\"{feedback}\"\n\nPlease correct this. Ensure the generated skills are highly specific and correct for the career \"{role}\", do not list unrelated or generic skills, and avoid the listed out-of-domain/contaminated skills!"
            
        return prompt_str

    def _call(self, prompt: str) -> str:
        compressed_messages = [{"role": "user", "content": prompt}]
        compressed_prompt = prompt

        if self.provider == "omniroute":
            resp = requests.post(
                f"{self.base_url.rstrip('/')}/chat/completions",
                json={
                    "model": self.model_name,
                    "messages": compressed_messages,
                    "temperature": 0.2,
                    "stream": False,
                },
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]

        try:
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
        except Exception as ollama_err:
            logger.warning("Ollama call failed: %s. Trying OmniRoute fallback...", ollama_err)
            try:
                settings = SettingsService.get()
                omniroute_base_url = settings.omniroute_base_url or "http://localhost:20128/v1"
                omniroute_model = settings.omniroute_model or "roadmap-agent"
                api_key = None
                if frappe.local and getattr(frappe.local, "initialised", False):
                    api_key = frappe.conf.get("omniroute_api_key")
                
                headers = {"Content-Type": "application/json"}
                if api_key:
                    headers["Authorization"] = f"Bearer {api_key}"
                
                resp = requests.post(
                    f"{omniroute_base_url.rstrip('/')}/chat/completions",
                    headers=headers,
                    json={
                        "model": omniroute_model,
                        "messages": compressed_messages,
                        "temperature": 0.2,
                        "stream": False,
                    },
                    timeout=self.timeout,
                )
                resp.raise_for_status()
                data = resp.json()
                logger.info("OmniRoute fallback call succeeded.")
                return data["choices"][0]["message"]["content"]
            except Exception as omni_err:
                logger.error("OmniRoute fallback also failed: %s", omni_err)
                raise ollama_err

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
        if "```json" in cleaned:
            start = cleaned.find("```json") + 7
            end = cleaned.find("```", start)
            if end != -1:
                cleaned = cleaned[start:end].strip()
        elif "```" in cleaned:
            start = cleaned.find("```") + 3
            end = cleaned.find("```", start)
            if end != -1:
                cleaned = cleaned[start:end].strip()
        else:
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start != -1 and end != -1 and start < end:
                cleaned = cleaned[start:end+1].strip()

        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise LLMServiceError(
                f"LLM did not return valid JSON: {exc}\nRaw (truncated): {raw_text[:300]}"
            ) from exc

        tiers = {
            "role": payload.get("role", ""),
            "foundation_skills": self._normalize_skill_list(payload.get("foundation_skills")),
            "core_domain_skills": self._normalize_skill_list(payload.get("core_domain_skills")),
            "industry_skills": self._normalize_skill_list(payload.get("industry_skills")),
            "emerging_skills": self._normalize_skill_list(payload.get("emerging_skills")),
        }
     
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
