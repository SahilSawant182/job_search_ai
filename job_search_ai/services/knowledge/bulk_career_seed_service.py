# -*- coding: utf-8 -*-
"""
BulkCareerSeedService — Seeds the Career Knowledge database and vector index
from the static JSON catalog. Should be run periodically or at startup.
"""

import json
import logging
import os
import uuid

import frappe
from job_search_ai.services.settings_service import SettingsService
from job_search_ai.services.ai.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)

_DEFAULT_CATALOG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "config",
    "career_seed_catalog.json",
)

class BulkCareerSeedService:
    def __init__(self, catalog_path: str = _DEFAULT_CATALOG_PATH):
        self.catalog_path = catalog_path
        self.settings = SettingsService.get()
        self.embedding_svc = EmbeddingService(self.settings)

        # For vector index directly instead of KnowledgeBuilder overhead
        from job_search_ai.services.ai.vector_index import VectorIndex
        self.vector_index = VectorIndex(self.settings)

    def run(self):
        logger.info("BulkCareerSeedService: Starting career knowledge seed...")
        try:
            with open(self.catalog_path, "r", encoding="utf-8") as f:
                catalog = json.load(f)
        except Exception as exc:
            logger.error("BulkCareerSeedService: Failed to load catalog: %s", exc)
            return

        added_count = 0
        updated_count = 0
        
        # We need to make sure the collection exists
        try:
            self.vector_index.create_collection()
        except Exception:
            pass

        for career in catalog:
            career_name = career["career_name"]
            
            # 1. Ensure Skill Doctypes exist
            all_skills = career.get("required_skills", []) + career.get("preferred_skills", [])
            for s in all_skills:
                s_clean = s.strip()
                if s_clean and not frappe.db.exists("Skill", s_clean):
                    try:
                        frappe.get_doc({
                            "doctype": "Skill",
                            "skill_name": s_clean,
                            "skill_category": "Technical",
                            "skill_level_schema": "Beginner→Expert"
                        }).insert(ignore_permissions=True)
                    except Exception:
                        pass

            # 2. Upsert Career Knowledge Doctype
            is_new = False
            ck_name = frappe.db.get_value("Career Knowledge", {"career_name": career_name}, "name")
            
            if not ck_name:
                is_new = True
                ck_doc = frappe.new_doc("Career Knowledge")
                ck_doc.career_name = career_name
            else:
                ck_doc = frappe.get_doc("Career Knowledge", ck_name)

            ck_doc.active = 1
            ck_doc.category = career["category"]
            ck_doc.industry = career["industry"]
            ck_doc.career_stage = career["career_stage"]
            ck_doc.future_demand = career["future_demand"]
            ck_doc.suitable_years = career.get("suitable_years", "")
            ck_doc.suitable_degrees = ",".join(career.get("suitable_degrees", []))
            ck_doc.suitable_branches = ",".join(career.get("suitable_branches", []))
            ck_doc.aliases = ",".join(career.get("interest_keywords", []))
            
            # Rebuild skills table
            ck_doc.set("skills", [])
            for s in career.get("required_skills", []):
                ck_doc.append("skills", {"skill_name": s, "skill_type": "Required"})
            for s in career.get("preferred_skills", []):
                ck_doc.append("skills", {"skill_name": s, "skill_type": "Preferred"})

            try:
                ck_doc.save(ignore_permissions=True)
                ck_name = ck_doc.name
                if is_new:
                    added_count += 1
                else:
                    updated_count += 1
            except Exception as exc:
                logger.error("Failed to save Career Knowledge for %s: %s", career_name, exc)
                continue

            # 3. Create Vector Embedding
            text_to_embed = (
                f"{career_name} | {career['category']} | {career['industry']} | "
                f"Required: {', '.join(career.get('required_skills', []))} | "
                f"Preferred: {', '.join(career.get('preferred_skills', []))} | "
                f"Interests: {', '.join(career.get('interest_keywords', []))}"
            )
            
            try:
                vector = self.embedding_svc.embed(text_to_embed)
                # Store in Qdrant with doc.name as the ID
                self.vector_index.upsert(
                    id=ck_name,
                    vector=vector,
                    payload={"career_name": career_name}
                )
            except Exception as exc:
                logger.error("Failed to create/store vector for %s: %s", career_name, exc)
                
        try:
            frappe.db.commit()
        except Exception:
            pass
            
        logger.info("BulkCareerSeedService: Done! Added %d, Updated %d careers.", added_count, updated_count)

def execute():
    """Hook for bench execute"""
    frappe.init(site="job_search_ai")
    frappe.connect()
    BulkCareerSeedService().run()
    frappe.destroy()
