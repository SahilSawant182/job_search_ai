# -*- coding: utf-8 -*-
import frappe
from job_search_ai.services.ai.vector_index import VectorIndex

def cleanup_all():
    print("Starting database cleanup...")
    
    # 1. Clean Qdrant career_knowledge collection
    try:
        vi = VectorIndex()
        client = vi._get_client()
        collection = vi._collection()
        if client.collection_exists(collection):
            print(f"Deleting Qdrant collection: {collection}")
            client.delete_collection(collection)
        print(f"Recreating Qdrant collection: {collection}")
        vi.create_collection()
    except Exception as exc:
        print(f"Error clearing Qdrant collection: {exc}")
        
    # 2. Delete all Career Knowledge docs in MariaDB
    try:
        docs = frappe.get_all("Career Knowledge", fields=["name"])
        print(f"Found {len(docs)} documents to delete in MariaDB.")
        for d in docs:
            frappe.delete_doc("Career Knowledge", d.name, force=True)
        frappe.db.commit()
        print("Successfully deleted all Career Knowledge documents from MariaDB.")
    except Exception as exc:
        print(f"Error deleting documents from MariaDB: {exc}")

    print("Database cleanup completed successfully!")
