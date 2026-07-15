# -*- coding: utf-8 -*-
# job_search_ai/services/knowledge/knowledge_refresh_service.py
#
# KnowledgeRefreshService
# -----------------------
# Orchestrates the background refresh of expired or marked Career Knowledge
# records.
#
# Responsibility
# --------------
#   1. Query active Career Knowledge records that have expired or need refresh.
#   2. Limit execution up to SettingsService.maximum_refresh_per_run.
#   3. Process records in batches defined by SettingsService.refresh_batch_size.
#   4. For each record:
#      - Build synthetic StudentProfile.
#      - Generate search queries via QueryBuilder.
#      - Fetch fresh articles from Tavily.
#      - Filter results via ResultFilter.
#      - Call KnowledgeBuilder to rebuild/update (which handles Qdrant and lifecycle).
#   5. Handle failures gracefully: continue processing remaining records if one fails.

from __future__ import annotations

import logging
import time
from typing import Any

import frappe
import frappe.utils
from job_search_ai.agents.career_trend.result_filter import ResultFilter
from job_search_ai.agents.career_trend.schemas import StudentProfile
from job_search_ai.agents.career_trend.tavily_service import TavilyService
from job_search_ai.services.knowledge.knowledge_builder import KnowledgeBuilder
from job_search_ai.services.settings_service import SettingsService

logger = logging.getLogger(__name__)


class KnowledgeRefreshService:
    """Service to automatically update stale or expired Career Knowledge records in the background."""

    def __init__(self, settings: SettingsService | None = None) -> None:
        if settings is None:
            settings = SettingsService.get()
        self._settings = settings

    def refresh(self) -> dict[str, Any]:
        """Query and refresh expired or marked Career Knowledge records.

        Returns a dictionary of execution metrics.
        """
        metrics = {
            "selected_count": 0,
            "success_count": 0,
            "failed_count": 0,
            "elapsed_seconds": 0.0,
        }

        # 1. Check if background refresh is enabled globally
        if not self._settings.enable_automatic_refresh:
            logger.info("KnowledgeRefreshService: automatic refresh is disabled in settings. Skipping run.")
            return metrics

        t_start = time.perf_counter()
        max_run = self._settings.maximum_refresh_per_run
        batch_size = self._settings.refresh_batch_size

        logger.info(
            "KnowledgeRefreshService starting: max_run=%d  batch_size=%d",
            max_run, batch_size
        )

        # 2. Query expired or marked records
        now_str = frappe.utils.now()
        # Retrieve name and career details. Case-independent active check.
        records = frappe.db.sql(
            """
            SELECT name, career_name, country, industry, category
            FROM `tabCareer Knowledge`
            WHERE active = 1
              AND (needs_refresh = 1 OR expires_on IS NULL OR expires_on <= %s)
            LIMIT %s
            """,
            (now_str, max_run),
            as_dict=True
        )

        if not records:
            logger.info("KnowledgeRefreshService: no records found needing refresh.")
            return metrics

        metrics["selected_count"] = len(records)
        logger.info("KnowledgeSelected: selected %d records for refresh", len(records))

        # 3. Process in batches
        for i in range(0, len(records), batch_size):
            batch = records[i:i + batch_size]
            logger.info("Processing refresh batch %d (size=%d)", (i // batch_size) + 1, len(batch))

            for row in batch:
                name = row["name"]
                career_name = row["career_name"]
                country = row["country"] or "India"

                logger.info("Refreshing Career Knowledge doc=%s  career=%s  country=%s", name, career_name, country)
                t_record = time.perf_counter()

                try:
                    # Construct a synthetic profile representing the career
                    student = StudentProfile(
                        degree="Engineering",
                        branch=career_name,
                        year=1,
                        country=country,
                        interests=[row["industry"]] if row["industry"] else [],
                        skills=[],
                    )


                    # Stage 1 — Generate search queries
                    from job_search_ai.agents.career_trend.query_builder import QueryBuilder
                    queries = QueryBuilder().build(student)

                    # Stage 2 — Execute Tavily search
                    raw_results = TavilyService().search(queries)

                    # Stage 3 — Filter results
                    filtered = ResultFilter().filter(raw_results)

                    if not filtered:
                        logger.warning("No search results found for career=%r. Skipping update.", career_name)
                        metrics["failed_count"] += 1
                        continue

                    # Stage 4 — Rebuild career knowledge (updates MariaDB, Qdrant, and lifecycle fields)
                    builder = KnowledgeBuilder(career_name=career_name, country=country)
                    built = builder.build(filtered)

                    # Explicitly log individual successes
                    elapsed = time.perf_counter() - t_record
                    metrics["success_count"] += 1
                    logger.info(
                        "KnowledgeRefreshed: successfully updated doc=%s  career=%s  "
                        "vector_dims=%d  elapsed=%.3fs",
                        built.doc_name, career_name, built.embedding_dim, elapsed
                    )

                except Exception as exc:
                    metrics["failed_count"] += 1
                    logger.exception(
                        "KnowledgeFailed: failed to refresh Career Knowledge doc=%s  career=%s  "
                        "error=%s",
                        name, career_name, exc
                    )

        # 4. Finalize execution metrics
        metrics["elapsed_seconds"] = time.perf_counter() - t_start
        logger.info(
            "KnowledgeRefreshService finished: selected=%d  success=%d  failed=%d  "
            "total_time=%.3fs",
            metrics["selected_count"],
            metrics["success_count"],
            metrics["failed_count"],
            metrics["elapsed_seconds"]
        )

        return metrics
