import frappe
from job_search_ai.services.knowledge.cleanup_database import cleanup_all
from job_search_ai.services.ai.vector_index import VectorIndex

def run():
    print("=== STARTING FULL DATABASE AND KNOWLEDGE BASE CLEANUP ===")
    
    # 1. Clean primary career_knowledge collection (Qdrant & MariaDB)
    cleanup_all()
    
    # 2. Clean additional Qdrant collections
    collections_to_recreate = [
        "career_knowledge_skill_cache",
        "skill_embeddings",
        "career_knowledge_job_description"
    ]
    
    for col_name in collections_to_recreate:
        print(f"Purging and recreating collection: {col_name}...")
        try:
            vi = VectorIndex(collection_name=col_name)
            vi.create_collection(recreate=True)
            print(f"Collection {col_name} successfully recreated.")
        except Exception as e:
            print(f"Failed to recreate collection {col_name}: {e}")
            
    print("=== FULL CLEANUP COMPLETED SUCCESSFULLY ===")
