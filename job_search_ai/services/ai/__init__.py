# -*- coding: utf-8 -*-
# job_search_ai/services/ai/__init__.py
#
# Reusable AI infrastructure services.
# These are framework-agnostic utilities shared across ALL agents:
#   Career Trend Agent, Skill Gap Agent, Learning Path Agent,
#   Resume Agent, Interview Agent, Master Agent, etc.
#
# Current services
# ----------------
#   EmbeddingService  — converts text → float vector via Ollama
#   VectorIndex       — abstraction layer over the vector database (Qdrant today)

from job_search_ai.services.ai.embedding_service import EmbeddingService, EmbeddingServiceError
from job_search_ai.services.ai.vector_index import VectorIndex, VectorIndexError, SearchResult

__all__ = [
    "EmbeddingService",
    "EmbeddingServiceError",
    "VectorIndex",
    "VectorIndexError",
    "SearchResult",
]
