"""
Write path for job-description knowledge.

Extracts a structured RoleProfile from filtered Tavily results via one LLM
call, then embeds + upserts it into the dedicated Qdrant collection so the
next request for this role is a Knowledge HIT.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

import requests

from job_search_ai.agents.job_description.llm_service import LLMService, LLMServiceError
from job_search_ai.agents.job_description.schemas import JobDescriptionRequest, RoleProfile

logger = logging.getLogger(__name__)


@dataclass
class BuildResult:
    is_new: bool
    profiles: list[RoleProfile]
    embedding_dim: int = 0


class JDKnowledgeBuilder:
    def __init__(self, settings):
        self.settings = settings
        self.qdrant_url = settings.qdrant_url.rstrip("/")
        self.collection = (settings.qdrant_collection_name or "career_knowledge") + "_job_description"
        self.embedding_model = settings.embedding_model
        self.ollama_endpoint = settings.ollama_endpoint
        self.vector_size = int(settings.embedding_dimension or 768)
        self.distance = settings.vector_distance or "Cosine"

    def build(self, request: JobDescriptionRequest, filtered_results: list) -> BuildResult:
        if not filtered_results:
            return BuildResult(is_new=False, profiles=[])

        profile = self._extract_profile(request, filtered_results)
        if profile is None:
            return BuildResult(is_new=False, profiles=[])

        vector = self._embed(f"{profile.role_name} {profile.summary}")
        if vector is None:
            # Extraction succeeded but embedding failed — still return the
            # profile so the caller has something to prompt the LLM with,
            # it just won't be cached for next time.
            return BuildResult(is_new=False, profiles=[profile])

        self._ensure_collection(len(vector))
        self._upsert(profile, vector)
        return BuildResult(is_new=True, profiles=[profile], embedding_dim=len(vector))

    def _extract_profile(self, request: JobDescriptionRequest, filtered_results: list) -> RoleProfile | None:
        snippets = "\n\n".join(
            f"- {getattr(r, 'title', '')}: {(getattr(r, 'content', '') or '')[:500]}"
            for r in filtered_results[:8]
        )
        extraction_prompt = (
            "Extract a structured job-role profile from the source snippets below. "
            "Respond with ONLY a JSON object, keys: role_name, category, summary, "
            "responsibilities (list of strings), required_skills (list of strings), "
            "preferred_skills (list of strings), qualifications (list of strings), "
            "tools_and_tech (list of strings).\n\n"
            f"Role: {request.role}\nSeniority: {request.seniority or 'unspecified'}\n\n"
            f"Source snippets:\n{snippets}"
        )
        try:
            llm = LLMService()
            raw = llm.call_raw(extraction_prompt)
            parsed = llm._parse(raw, request)  # reuses the same JSON parsing/validation
        except LLMServiceError as exc:
            logger.warning("JDKnowledgeBuilder: extraction failed (%s)", exc)
            return None

        return RoleProfile(
            role_name=parsed.title or request.role,
            category=request.department or "General",
            seniority=request.seniority or "Mid",
            summary=parsed.summary,
            responsibilities=parsed.responsibilities,
            required_skills=parsed.required_skills,
            preferred_skills=parsed.preferred_skills,
            qualifications=parsed.qualifications,
            source="web",
        )

    def _embed(self, text: str) -> list[float] | None:
        try:
            resp = requests.post(
                self.ollama_endpoint.replace("/api/generate", "/api/embeddings"),
                json={"model": self.embedding_model, "prompt": text},
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json().get("embedding")
        except Exception as exc:  # noqa: BLE001
            logger.warning("JDKnowledgeBuilder: embedding failed (%s)", exc)
            return None

    def _ensure_collection(self, dim: int) -> None:
        """Create the JD collection on first use if it doesn't exist yet."""
        try:
            check = requests.get(f"{self.qdrant_url}/collections/{self.collection}", timeout=10)
            if check.status_code == 200:
                return
            requests.put(
                f"{self.qdrant_url}/collections/{self.collection}",
                json={"vectors": {"size": dim, "distance": self.distance}},
                timeout=15,
            )
            logger.info("JDKnowledgeBuilder: created Qdrant collection %r (dim=%d, distance=%s)",
                        self.collection, dim, self.distance)
        except Exception as exc:  # noqa: BLE001
            logger.warning("JDKnowledgeBuilder: could not ensure collection %r (%s)",
                            self.collection, exc)

    def _upsert(self, profile: RoleProfile, vector: list[float]) -> None:
        point = {
            "id": str(uuid.uuid4()),
            "vector": vector,
            "payload": {
                "role_name": profile.role_name,
                "category": profile.category,
                "seniority": profile.seniority,
                "summary": profile.summary,
                "responsibilities": profile.responsibilities,
                "required_skills": profile.required_skills,
                "preferred_skills": profile.preferred_skills,
                "qualifications": profile.qualifications,
                "tools_and_tech": profile.tools_and_tech,
            },
        }
        try:
            requests.put(
                f"{self.qdrant_url}/collections/{self.collection}/points",
                json={"points": [point]},
                timeout=15,
            )
        except Exception as exc:  # noqa: BLE001
            # Best-effort, matches CareerTrendAgent's invariant: the user
            # still gets a response even if KB persistence fails.
            logger.warning("JDKnowledgeBuilder: Qdrant upsert failed (%s)", exc)