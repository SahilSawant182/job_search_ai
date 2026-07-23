# -*- coding: utf-8 -*-
# Copyright (c) 2026, Sahil Sawant and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class SkillMaster(Document):
    def on_update(self):
        self._sync_skill_embedding()
        self._invalidate_cache()

    def on_trash(self):
        self._delete_skill_embedding()
        self._invalidate_cache()

    def _invalidate_cache(self):
        try:
            from job_search_ai.services.skill_gap.normalizer import invalidate_normalization_cache
            invalidate_normalization_cache()
        except Exception:
            pass

    def _sync_skill_embedding(self):
        try:
            from job_search_ai.services.skill_gap.skill_embedding_index import SkillEmbeddingBuilder

            SkillEmbeddingBuilder().sync_skill(self.name)
        except Exception:
            frappe.log_error(
                title="Skill Embedding Sync Failed",
                message=frappe.get_traceback(),
            )

    def _delete_skill_embedding(self):
        try:
            from job_search_ai.services.skill_gap.skill_embedding_index import SkillEmbeddingBuilder

            SkillEmbeddingBuilder().delete_skill(self.name)
        except Exception:
            frappe.log_error(
                title="Skill Embedding Delete Failed",
                message=frappe.get_traceback(),
            )
