# -*- coding: utf-8 -*-
# job_search_ai/services/knowledge/__init__.py
#
# Knowledge services — higher-level operations that combine raw AI
# infrastructure (EmbeddingService, VectorIndex) with MariaDB persistence.

from job_search_ai.services.knowledge.knowledge_builder import (
    KnowledgeBuilder,
    KnowledgeBuilderError,
    BuiltKnowledge,
)
from job_search_ai.services.knowledge.knowledge_retriever import (
    KnowledgeRetriever,
    KnowledgeRetrieverError,
    RetrievedKnowledge,
)
from job_search_ai.services.knowledge.knowledge_lifecycle import (
    KnowledgeLifecycle,
)
from job_search_ai.services.knowledge.knowledge_refresh_service import (
    KnowledgeRefreshService,
)

__all__ = [
    "KnowledgeBuilder",
    "KnowledgeBuilderError",
    "BuiltKnowledge",
    "KnowledgeRetriever",
    "KnowledgeRetrieverError",
    "RetrievedKnowledge",
    "KnowledgeLifecycle",
    "KnowledgeRefreshService",
]



