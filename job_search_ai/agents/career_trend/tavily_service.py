"""
TavilyService — real Tavily Search API integration with parallel execution.

Responsibility:
    Accept a list of query strings and return a list of SearchResult objects
    by calling the Tavily Search API concurrently using a ThreadPoolExecutor.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.request
import urllib.error
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Final

from job_search_ai.agents.career_trend.schemas import SearchResult
from job_search_ai.services.settings_service import SettingsService

logger = logging.getLogger(__name__)

# Tavily API endpoints and request defaults
_TAVILY_API_URL: Final[str] = "https://api.tavily.com/search"
_SEARCH_TIMEOUT_SECONDS: Final[float] = 15.0


class TavilyService:
    """
    Search service using the live Tavily Search API with concurrent requests.

    Usage::

        service = TavilyService()
        results = service.search(["AI careers India", "Future of ML"])
    """

    def search(self, queries: list[str]) -> list[SearchResult]:
        """
        Search for each query using Tavily API concurrently.

        Uses ThreadPoolExecutor to run requests in parallel. Continues if some
        queries fail, raising RuntimeError only if all queries failed.
        """
        if not queries:
            raise ValueError("TavilyService.search requires at least one query.")

        settings = SettingsService.get()
        api_key = settings.get_password("tavily_api_key")
        if not api_key or not api_key.strip():
            raise ValueError(
                "Tavily API Key is not configured. The administrator must configure "
                "the 'Tavily API Key' in the 'Job Search AI Settings' page in the Frappe Desk."
            )

        logger.info("Calling Tavily concurrently for %d queries", len(queries))
        start_time = time.perf_counter()

        all_results: list[SearchResult] = []
        failed_queries: list[tuple[str, str]] = []

        max_workers = min(len(queries), settings.parallel_search_workers)

        # Run search queries in parallel
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_query = {
                executor.submit(self._search_single_query, query, api_key, settings.maximum_search_results_per_query): query
                for query in queries
            }

            for future in as_completed(future_to_query):
                query = future_to_query[future]
                try:
                    results = future.result()
                    all_results.extend(results)
                except Exception as exc:
                    logger.warning("Failed to search for query %r: %s", query, exc)
                    failed_queries.append((query, str(exc)))

        search_time = time.perf_counter() - start_time
        logger.info(
            "Parallel search completed in %.3f seconds. Retrieved %d raw results.",
            search_time,
            len(all_results),
        )

        if len(failed_queries) == len(queries):
            errors_str = "; ".join(f"'{q}': {err}" for q, err in failed_queries)
            raise RuntimeError(
                f"All Tavily searches failed. Errors: {errors_str}"
            )

        return all_results

    def _search_single_query(self, query: str, api_key: str, max_results: int) -> list[SearchResult]:
        """
        Execute a single POST request to the Tavily search endpoint.
        """
        logger.info("Searching: %s", query)

        payload = {
            "api_key": api_key,
            "query": query,
            "search_depth": "advanced",
            "max_results": max_results,
            "include_images": False,
            "include_answer": False,
            "include_raw_content": False,
        }

        req = urllib.request.Request(
            _TAVILY_API_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "User-Agent": "job_search_ai-agent/1.0",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=_SEARCH_TIMEOUT_SECONDS) as response:
                if response.status != 200:
                    raise RuntimeError(f"Tavily API responded with HTTP status {response.status}")

                body = response.read().decode("utf-8")
                data = json.loads(body)

                results: list[SearchResult] = []
                for item in data.get("results", []):
                    url_str = item.get("url", "")
                    res = SearchResult(
                        title=item.get("title", ""),
                        url=url_str,
                        content=item.get("content", ""),
                        source=self._extract_source(url_str),
                        score=float(item.get("score", 0.0)),
                    )
                    results.append(res)
                return results

        except urllib.error.HTTPError as err:
            try:
                err_body = err.read().decode("utf-8")
                logger.debug("Tavily API HTTP Error body: %s", err_body)
            except Exception:
                err_body = ""
            raise RuntimeError(
                f"Tavily HTTP error {err.code}: {err.reason}. {err_body}"
            ) from err
        except urllib.error.URLError as err:
            raise RuntimeError(f"Tavily connection error: {err.reason}") from err
        except Exception as err:
            raise RuntimeError(f"Unexpected Tavily search error: {err}") from err

    def _extract_source(self, url: str) -> str:
        """Extract a clean domain name from a URL to use as the source."""
        if not url:
            return "Web Search"
        try:
            parsed = urlparse(url)
            netloc = parsed.netloc
            if netloc.startswith("www."):
                return netloc[4:]
            return netloc or "Web Search"
        except Exception:
            return "Web Search"
