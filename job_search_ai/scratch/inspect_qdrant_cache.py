import frappe
import requests
from job_search_ai.services.settings_service import SettingsService
from job_search_ai.agents.skill_agent.knowledge_cache import SkillKnowledgeCache

def inspect_cache():
    settings = SettingsService.get()
    cache = SkillKnowledgeCache(settings)
    
    print("Collection:", cache.collection)
    
    # Scroll / Search all points
    url = f"{cache.qdrant_url}/collections/{cache.collection}/points/scroll"
    resp = requests.post(url, json={"limit": 100, "with_payload": True}, timeout=10)
    res = resp.json().get("result", {})
    points = res.get("points", [])
    
    print(f"Total points in cache: {len(points)}")
    for p in points:
        payload = p.get("payload", {})
        print(f"\nID: {p.get('id')}")
        print(f"Role Name: {payload.get('role_name')}")
        print(f"Foundation: {payload.get('foundation_skills')}")
        print(f"Core Domain: {payload.get('core_domain_skills')}")
        print(f"Industry: {payload.get('industry_skills')}")
        print(f"Emerging: {payload.get('emerging_skills')}")
        print(f"Schema Version: {payload.get('schema_version')}")

if __name__ == "__main__":
    inspect_cache()
