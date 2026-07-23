# -*- coding: utf-8 -*-
# Copyright (c) 2026, Sahil Sawant and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class SkillRelationship(Document):
    def on_update(self):
        self._invalidate_cache()

    def on_trash(self):
        self._invalidate_cache()

    def _invalidate_cache(self):   
        try:
            from job_search_ai.services.skill_gap.relationship import invalidate_relationship_cache
            invalidate_relationship_cache()
        except Exception:
            pass
