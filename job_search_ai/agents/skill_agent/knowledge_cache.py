"""
Vector-DB cache for skill profiles.

Uses the same Qdrant server as career_trend / job_description agents, but a
DEDICATED collection: "<qdrant_collection_name>_skill_cache". A single class
handles both read (similarity search) and write (embed + upsert) since
there's no separate extraction step here — the LLM generates the skills
directly, so there's nothing intermediate to persist between stages.
"""

from __future__ import annotations

import logging
import uuid

import requests

from job_search_ai.agents.skill_agent.schemas import SkillProfile

logger = logging.getLogger(__name__)

SKILL_COLLECTION_SUFFIX = "_skill_cache"


class SkillKnowledgeCache:

    def __init__(self, settings):
        self.settings = settings
        self.qdrant_url = settings.qdrant_url.rstrip("/")
        self.collection = (settings.qdrant_collection_name or "career_knowledge") + SKILL_COLLECTION_SUFFIX
        self.embedding_model = settings.embedding_model
        self.ollama_endpoint = settings.ollama_endpoint
        self.vector_size = int(settings.embedding_dimension or 768)
        self.distance = settings.vector_distance or "Cosine"
        self.top_k = int(settings.max_retrieved_knowledge or 5)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------
    def lookup(self, role: str, seniority: str | None = None) -> SkillProfile | None:
        vector = self._embed(self._query_text(role))
        if vector is None:
            return None

        try:
            resp = requests.post(
                f"{self.qdrant_url}/collections/{self.collection}/points/search",
                json={"vector": vector, "limit": 5, "with_payload": True},
                timeout=15,
            )
            resp.raise_for_status()
            hits = resp.json().get("result", [])
        except Exception as exc:  # noqa: BLE001
            # Includes "collection doesn't exist yet" on first-ever call — treat as MISS.
            logger.warning("SkillKnowledgeCache: Qdrant search failed (%s)", exc)
            return None

        for hit in hits:
            score = hit.get("score", 0.0)
            if score < 0.85:
                continue

            payload = hit.get("payload", {})
            # If payload only has the old format, contains any of the deleted fields,
            # or is missing the new schema_version, skip it to find a newer clean cached profile.
            if (
                "foundation_skills" not in payload
                or "professional_skills" in payload
                or "recommended_tools" in payload
                or payload.get("schema_version") != "v3"
            ):
                continue

            return SkillProfile(
                role_name=payload.get("role_name", role),
                foundation_skills=payload.get("foundation_skills", []),
                core_domain_skills=payload.get("core_domain_skills", []),
                industry_skills=payload.get("industry_skills", []),
                emerging_skills=payload.get("emerging_skills", []),
                similarity=score,
                source="cache",
            )

        return None

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------
    def store(self, profile: SkillProfile) -> None:
        vector = self._embed(self._query_text(profile.role_name))
        if vector is None:
            logger.warning("SkillKnowledgeCache: embedding failed, skipping cache write for %r",
                            profile.role_name)
            return

        self._ensure_collection(len(vector))

        point = {
            "id": str(uuid.uuid4()),
            "vector": vector,
            "payload": {
                "role_name": profile.role_name,
                "foundation_skills": profile.foundation_skills,
                "core_domain_skills": profile.core_domain_skills,
                "industry_skills": profile.industry_skills,
                "emerging_skills": profile.emerging_skills,
                "schema_version": "v3",
            },
        }
        try:
            requests.put(
                f"{self.qdrant_url}/collections/{self.collection}/points",
                json={"points": [point]},
                timeout=15,
            )
        except Exception as exc:  # noqa: BLE001
            # Best-effort: caller still gets the generated skills even if caching fails.
            logger.warning("SkillKnowledgeCache: Qdrant upsert failed (%s)", exc)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _query_text(self, role: str, seniority: str | None = None) -> str:
        parts = [role, seniority or ""]
        return " ".join(p for p in parts if p)

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
            logger.warning("SkillKnowledgeCache: embedding failed (%s)", exc)
            return None

    def _ensure_collection(self, dim: int) -> None:
        try:
            check = requests.get(f"{self.qdrant_url}/collections/{self.collection}", timeout=10)
            if check.status_code == 200:
                return
            requests.put(
                f"{self.qdrant_url}/collections/{self.collection}",
                json={"vectors": {"size": dim, "distance": self.distance}},
                timeout=15,
            )
            logger.info("SkillKnowledgeCache: created Qdrant collection %r (dim=%d, distance=%s)",
                        self.collection, dim, self.distance)
        except Exception as exc:  # noqa: BLE001
            logger.warning("SkillKnowledgeCache: could not ensure collection %r (%s)",
                            self.collection, exc)