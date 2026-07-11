"""
ResultFilter — cleans and deduplicates raw search results.

Responsibility:
    Accept a list of SearchResult objects, remove noise, and return a
    clean, deduplicated list suitable for prompt construction.

Filtering and Ranking rules:
    1. Drop results with empty content.
    2. Drop duplicate URLs.
    3. Drop duplicate titles.
    4. Sort results descending using their Tavily relevance score.
    5. Limit the final result list to a maximum of 6 (MAX_RESULTS_FOR_LLM).
"""

from __future__ import annotations

import logging
from typing import Final

from job_search_ai.agents.career_trend.schemas import SearchResult
from job_search_ai.services.settings_service import SettingsService

logger = logging.getLogger(__name__)

class ResultFilter:
    """
    Cleans, ranks, and truncates a raw list of SearchResult objects.

    Usage::

        filtered = ResultFilter().filter(raw_results)
    """

    def filter(self, results: list[SearchResult]) -> list[SearchResult]:
        """
        Remove duplicates, sort by relevance score, and return top results.

        Args:
            results: Raw SearchResult list from the search service.

        Returns:
            A sorted, deduplicated list containing at most maximum_results_sent_to_llm
            SearchResult objects.

        Raises:
            ValueError: If ``results`` is None.
        """
        if results is None:
            raise ValueError("ResultFilter.filter received None instead of a list.")

        settings = SettingsService.get()
        max_results = settings.maximum_results_sent_to_llm

        logger.info("Filtering %d raw search results.", len(results))

        seen_urls: set[str] = set()
        seen_titles: set[str] = set()
        cleaned: list[SearchResult] = []

        for result in results:
            # Rule 1: Skip empty content.
            if not result.content or not result.content.strip():
                logger.debug("Dropped result with empty content: url=%r", result.url)
                continue

            # Rule 2: Skip duplicate URLs (normalised).
            normalised_url = result.url.strip().lower()
            if normalised_url in seen_urls:
                logger.debug("Dropped duplicate URL: %r", result.url)
                continue

            # Rule 3: Skip duplicate titles (normalised).
            normalised_title = result.title.strip().lower()
            if normalised_title in seen_titles:
                logger.debug("Dropped duplicate title: %r", result.title)
                continue

            seen_urls.add(normalised_url)
            seen_titles.add(normalised_title)
            cleaned.append(result)

        # Rule 4: Sort descending by relevance score (proper attribute)
        cleaned.sort(key=lambda r: r.score, reverse=True)

        # Rule 5: Keep only top max_results results
        final_results = cleaned[:max_results]

        logger.info(
            "Filtering complete: %d results kept out of %d (limit: %d).",
            len(final_results),
            len(results),
            max_results,
        )
        return final_results
