# -*- coding: utf-8 -*-
# job_search_ai/services/ai/embedding_service.py
#
# EmbeddingService
# ----------------
# Single-responsibility service: convert a text string into a float vector
# by calling the Ollama /api/embed endpoint.
#
# Architecture
# ------------
#   text  ──►  EmbeddingService.embed()  ──►  Ollama /api/embed  ──►  list[float]
#
# This service is intentionally ignorant of:
#   - Qdrant / vector stores
#   - MariaDB / Frappe DocTypes
#   - Business concepts (careers, skills, students, …)
#
# It is designed to be reused by every agent in the Job Search AI system.
#
# Configuration (read via SettingsService)
# ----------------------------------------
#   embedding_model          — Ollama model name  (default: nomic-embed-text)
#   ollama_base_url          — scheme + host + port derived from ollama_endpoint
#   embedding_timeout_seconds — HTTP timeout       (default: llm_timeout_seconds)
#
# Ollama API used
# ---------------
#   POST /api/embed
#   Body : { "model": "<model>", "input": "<text>" }
#   Response: { "embeddings": [[f1, f2, …, f768]] }
#   Verified against Ollama 0.30.10 with nomic-embed-text (768-dim).

from __future__ import annotations

import logging
import time
import urllib.parse
from typing import TYPE_CHECKING

import requests

if TYPE_CHECKING:
    from job_search_ai.services.settings_service import SettingsService

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public exception
# ---------------------------------------------------------------------------

class EmbeddingServiceError(Exception):
    """Raised by EmbeddingService for any embedding failure.

    Wraps lower-level exceptions (network errors, bad responses, …) into a
    single, predictable error type that callers can handle uniformly.
    """


# ---------------------------------------------------------------------------
# EmbeddingService
# ---------------------------------------------------------------------------

class EmbeddingService:
    """Convert text into a dense float vector using an Ollama embedding model.

    Public API
    ----------
    >>> svc = EmbeddingService()
    >>> vector: list[float] = svc.embed("Machine learning engineer")

    The vector dimension depends on the configured model.
    For *nomic-embed-text* that is 768 dimensions.

    Parameters
    ----------
    settings : SettingsService | None
        Optional settings override (useful for testing).  When *None*, the
        global singleton ``SettingsService.get()`` is used.
    """

    # Ollama embedding endpoint path (Ollama ≥ 0.1.28 / verified on 0.30.10)
    _EMBED_PATH = "/api/embed"

    def __init__(self, settings: "SettingsService | None" = None) -> None:
        if settings is None:
            # Lazy import to avoid circular imports in test environments
            from job_search_ai.services.settings_service import SettingsService
            settings = SettingsService.get()

        self._settings = settings

    # ------------------------------------------------------------------
    # Public method
    # ------------------------------------------------------------------

    def embed(self, text: str) -> list[float]:
        """Embed *text* and return a dense float vector.

        Parameters
        ----------
        text : str
            Non-empty, non-whitespace text to embed.

        Returns
        -------
        list[float]
            The embedding vector produced by the configured Ollama model.

        Raises
        ------
        EmbeddingServiceError
            If *text* is invalid, the Ollama server is unreachable, returns a
            non-200 response, or the response is missing the expected payload.
        """
        self._validate_text(text)

        model = self._settings.embedding_model
        url = self._build_url()
        timeout = self._settings.embedding_timeout_seconds

        logger.info(
            "EmbeddingService: started — model=%r  text_len=%d  url=%s",
            model,
            len(text),
            url,
        )

        t_start = time.perf_counter()
        try:
            response = requests.post(
                url,
                json={"model": model, "input": text},
                timeout=timeout,
                headers={"Content-Type": "application/json"},
            )
        except requests.exceptions.ConnectionError as exc:
            raise EmbeddingServiceError(
                f"EmbeddingService: cannot connect to Ollama at {url!r}. "
                f"Check ollama_endpoint in Job Search AI Settings."
            ) from exc
        except requests.exceptions.Timeout as exc:
            raise EmbeddingServiceError(
                f"EmbeddingService: request timed out after {timeout}s. "
                f"Consider increasing embedding_timeout_seconds."
            ) from exc
        except requests.exceptions.RequestException as exc:
            raise EmbeddingServiceError(
                f"EmbeddingService: HTTP request failed — {exc}"
            ) from exc

        elapsed = time.perf_counter() - t_start

        self._check_http_status(response, url)
        vector = self._parse_response(response)

        logger.info(
            "EmbeddingService: finished — model=%r  dims=%d  elapsed=%.3fs",
            model,
            len(vector),
            elapsed,
        )

        return vector

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _validate_text(self, text: str) -> None:
        """Raise EmbeddingServiceError if *text* is None, empty, or whitespace-only."""
        if text is None:
            raise EmbeddingServiceError(
                "EmbeddingService.embed() received None. "
                "Provide a non-empty string."
            )
        if not isinstance(text, str):
            raise EmbeddingServiceError(
                f"EmbeddingService.embed() expected str, got {type(text).__name__}."
            )
        if not text.strip():
            raise EmbeddingServiceError(
                "EmbeddingService.embed() received an empty or whitespace-only string. "
                "Provide meaningful text."
            )

    def _build_url(self) -> str:
        """Construct the full embedding endpoint URL."""
        base = self._settings.ollama_base_url.rstrip("/")
        return base + self._EMBED_PATH

    def _check_http_status(self, response: requests.Response, url: str) -> None:
        """Raise EmbeddingServiceError for non-200 HTTP responses."""
        if response.status_code != 200:
            raise EmbeddingServiceError(
                f"EmbeddingService: Ollama returned HTTP {response.status_code} "
                f"from {url!r}. Body: {response.text[:300]!r}"
            )

    def _parse_response(self, response: requests.Response) -> list[float]:
        """Parse the Ollama /api/embed response and return the embedding vector.

        Expected response shape::

            {
              "model": "nomic-embed-text",
              "embeddings": [[0.028, 0.011, …]],
              "total_duration": …,
              …
            }

        The outer list holds one embedding per input string.  Since we always
        send a single string, we return ``embeddings[0]``.
        """
        try:
            body = response.json()
        except ValueError as exc:
            raise EmbeddingServiceError(
                f"EmbeddingService: Ollama response is not valid JSON. "
                f"Raw body: {response.text[:300]!r}"
            ) from exc

        embeddings = body.get("embeddings")
        if not embeddings:
            raise EmbeddingServiceError(
                f"EmbeddingService: 'embeddings' key is missing or empty in Ollama response. "
                f"Keys found: {list(body.keys())}"
            )

        if not isinstance(embeddings, list) or not embeddings[0]:
            raise EmbeddingServiceError(
                "EmbeddingService: 'embeddings[0]' is empty or not a list."
            )

        vector: list[float] = embeddings[0]
        if not all(isinstance(v, (int, float)) for v in vector):
            raise EmbeddingServiceError(
                "EmbeddingService: embedding vector contains non-numeric values."
            )

        return vector
