# -*- coding: utf-8 -*-
# job_search_ai/services/knowledge/reindex_knowledge.py

import frappe
from job_search_ai.services.knowledge.knowledge_builder import KnowledgeBuilder

def reindex_all_knowledge():
    """
    Load all Career Knowledge documents, re-generate their vector embeddings
    using the new non-prose schema, and upsert them to Qdrant.
    """
    print("Starting Career Knowledge database re-indexing...")
    docs = frappe.get_all("Career Knowledge", fields=["name"])
    print(f"Found {len(docs)} documents to process.")

    success_count = 0
    error_count = 0

    for index, doc_ref in enumerate(docs, 1):
        name = doc_ref["name"]
        try:
            doc = frappe.get_doc("Career Knowledge", name)
            skills = [s.skill_name for s in doc.skills or []]

            extracted = {
                "career_name": doc.career_name,
                "industry": doc.industry,
                "category": doc.category,
                "skills": skills
            }

            builder = KnowledgeBuilder(
                career_name=doc.career_name,
                country=doc.country
            )

            # Generate new embed text (without prose summary, with category)
            embed_text = builder._build_embed_text(extracted)

            # Generate new vector embedding
            vector = builder._embed(embed_text)

            # Upsert into Qdrant vector index
            builder._index(
                doc_name=doc.name,
                vector=vector,
                payload={
                    "career_name": doc.career_name,
                    "country": doc.country or "",
                    "industry": doc.industry or "",
                    "doc_name": doc.name,
                }
            )

            # Update embedding hash in MariaDB
            builder._update_embedding_hash(doc.name, vector)

            print(f"[{index}/{len(docs)}] Successfully re-indexed {doc.name} - '{doc.career_name}'")
            success_count += 1

        except Exception as e:
            print(f"[{index}/{len(docs)}] Failed to re-index {name}: {e}")
            error_count += 1

    print("--------------------------------------------------")
    print(f"Re-indexing complete: {success_count} succeeded, {error_count} failed.")

if __name__ == "__main__":
    reindex_all_knowledge()
