# -*- coding: utf-8 -*-
# job_search_ai/services/knowledge/export_knowledge.py
#
# ExportKnowledge — export all Career Knowledge documents and Qdrant vectors
# to JSON backup files before running cleanup_all().
#
# Usage (via bench):
#   bench --site <site> execute job_search_ai.services.knowledge.export_knowledge.export_all
#
# Output files (written to the site's private/files directory):
#   career_knowledge_backup_<timestamp>.json     — all MariaDB Career Knowledge docs
#   qdrant_backup_<timestamp>.json               — all Qdrant vector payloads

from __future__ import annotations

import json
import logging
import os
from datetime import datetime

import frappe

logger = logging.getLogger(__name__)


def export_all(output_dir: str | None = None) -> dict:
    """
    Export all Career Knowledge documents and Qdrant vector payloads to JSON.

    Parameters
    ----------
    output_dir : str | None
        Directory to write backup files into.
        Defaults to `<site>/private/files/career_knowledge_backups/`.

    Returns
    -------
    dict with keys:
        mariadb_path  — absolute path of the MariaDB backup JSON
        qdrant_path   — absolute path of the Qdrant backup JSON
        mariadb_count — number of documents exported
        qdrant_count  — number of Qdrant points exported
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if output_dir is None:
        site_path = frappe.get_site_path()
        output_dir = os.path.join(site_path, "private", "files", "career_knowledge_backups")

    os.makedirs(output_dir, exist_ok=True)

    mariadb_path = os.path.join(output_dir, f"career_knowledge_backup_{timestamp}.json")
    qdrant_path  = os.path.join(output_dir, f"qdrant_backup_{timestamp}.json")

    # ── 1. Export MariaDB Career Knowledge documents ──────────────────────
    mariadb_docs = _export_mariadb(mariadb_path)

    # ── 2. Export Qdrant vector payloads ──────────────────────────────────
    qdrant_points = _export_qdrant(qdrant_path)

    result = {
        "mariadb_path":  mariadb_path,
        "qdrant_path":   qdrant_path,
        "mariadb_count": len(mariadb_docs),
        "qdrant_count":  len(qdrant_points),
        "timestamp":     timestamp,
    }

    print(f"\n{'='*60}")
    print(f"  Career Knowledge Backup — {timestamp}")
    print(f"{'='*60}")
    print(f"  MariaDB: {len(mariadb_docs)} documents → {mariadb_path}")
    print(f"  Qdrant:  {len(qdrant_points)} vectors  → {qdrant_path}")
    print(f"{'='*60}\n")

    return result


def _export_mariadb(output_path: str) -> list[dict]:
    """Export all Career Knowledge docs from MariaDB to JSON."""
    doc_names = frappe.get_all("Career Knowledge", fields=["name"])
    documents = []

    for row in doc_names:
        try:
            doc = frappe.get_doc("Career Knowledge", row["name"])
            doc_data = doc.as_dict()

            # Convert datetime objects to ISO strings for JSON serialisation
            for key, val in doc_data.items():
                if hasattr(val, "isoformat"):
                    doc_data[key] = val.isoformat()

            # Serialise child table rows similarly
            for child_key in ("skills", "companies", "sources"):
                child_list = doc_data.get(child_key, [])
                for child in child_list:
                    for k, v in child.items():
                        if hasattr(v, "isoformat"):
                            child[k] = v.isoformat()

            documents.append(doc_data)
        except Exception as exc:
            logger.warning("export_mariadb: could not export %r: %s", row["name"], exc)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(documents, f, indent=2, ensure_ascii=False)

    logger.info("export_mariadb: exported %d documents to %s", len(documents), output_path)
    return documents


def _export_qdrant(output_path: str) -> list[dict]:
    """Export all Qdrant vector payloads to JSON (IDs + payloads, no raw vectors)."""
    from job_search_ai.services.ai.vector_index import VectorIndex

    try:
        vi = VectorIndex()
        client = vi._get_client()
        collection = vi._collection()

        if not client.collection_exists(collection):
            print(f"  Qdrant collection '{collection}' does not exist. Skipping Qdrant export.")
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump([], f)
            return []

        # Scroll through all points (no limit — export everything)
        points = []
        offset = None
        while True:
            response, next_offset = client.scroll(
                collection_name=collection,
                limit=100,
                offset=offset,
                with_payload=True,
                with_vectors=False,  # payloads only — vectors are regeneratable
            )
            for point in response:
                points.append({
                    "id":      str(point.id),
                    "payload": point.payload or {},
                })
            if next_offset is None:
                break
            offset = next_offset

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(points, f, indent=2, ensure_ascii=False)

        logger.info("export_qdrant: exported %d points to %s", len(points), output_path)
        return points

    except Exception as exc:
        logger.error("export_qdrant: failed — %s", exc)
        print(f"  WARNING: Qdrant export failed: {exc}")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump([], f)
        return []


def export_and_cleanup() -> None:
    """
    Convenience function: export first, then run cleanup_all().
    Always call this instead of cleanup_all() directly when you have data worth keeping.
    """
    print("Step 1: Backing up existing Career Knowledge data...")
    result = export_all()

    if result["mariadb_count"] == 0 and result["qdrant_count"] == 0:
        print("  Nothing to back up. Proceeding directly to cleanup.")
    else:
        print(f"  Backup complete: {result['mariadb_count']} docs, {result['qdrant_count']} vectors.")

    print("\nStep 2: Cleaning up databases...")
    from job_search_ai.services.knowledge.cleanup_database import cleanup_all
    cleanup_all()
