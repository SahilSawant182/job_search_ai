"""
Vector-search read path for job-description knowledge.

Uses the SAME Qdrant server as career_trend (settings.qdrant_url) but a
DEDICATED collection (`<qdrant_collection_name>_job_description`) so role
profiles never mix with career-trend career profiles in similarity search.
"""

from __future__ import annotations

import logging

import requests

from job_search_ai.agents.job_description.schemas import JobDescriptionRequest, RoleProfile

logger = logging.getLogger(__name__)

JD_COLLECTION_SUFFIX = "_job_description"


class JDKnowledgeRetriever:

    def __init__(self, settings):
        self.settings = settings
        self.qdrant_url = settings.qdrant_url.rstrip("/")
        self.collection = (settings.qdrant_collection_name or "career_knowledge") + JD_COLLECTION_SUFFIX
        self.embedding_model = settings.embedding_model
        self.ollama_endpoint = settings.ollama_endpoint
        self.top_k = int(settings.max_retrieved_knowledge or 5)

    def retrieve(self, request: JobDescriptionRequest) -> list[RoleProfile]:
        vector = self._embed(self._query_text(request))
        if vector is None:
            return []

        try:
            resp = requests.post(
                f"{self.qdrant_url}/collections/{self.collection}/points/search",
                json={"vector": vector, "limit": self.top_k, "with_payload": True},
                timeout=15,
            )
            resp.raise_for_status()
            hits = resp.json().get("result", [])
        except Exception as exc:  # noqa: BLE001
            # Includes the case where the collection doesn't exist yet
            # (first-ever request for this role type) — treat as a MISS.
            logger.warning("JDKnowledgeRetriever: Qdrant search failed (%s)", exc)
            return []

        profiles = []
        for hit in hits:
            payload = hit.get("payload", {})
            profiles.append(RoleProfile(
                role_name=payload.get("role_name", request.role),
                category=payload.get("category", "General"),
                seniority=payload.get("seniority", request.seniority or "Mid"),
                summary=payload.get("summary", ""),
                responsibilities=payload.get("responsibilities", []),
                required_skills=payload.get("required_skills", []),
                preferred_skills=payload.get("preferred_skills", []),
                qualifications=payload.get("qualifications", []),
                tools_and_tech=payload.get("tools_and_tech", []),
                similarity=hit.get("score", 0.0),   
                source="knowledge",
            ))
        return profiles

    def _query_text(self, request: JobDescriptionRequest) -> str:
        parts = [request.role, request.seniority or "", request.department or ""]
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
            logger.warning("JDKnowledgeRetriever: embedding failed (%s)", exc)
            return None