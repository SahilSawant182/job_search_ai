# -*- coding: utf-8 -*-
# Copyright (c) 2026, Sahil Sawant and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class CareerKnowledge(Document):

	def validate(self):
		self._validate_career_name()
		self._validate_salary_range()
		self._set_defaults()

	def _validate_career_name(self):
		"""career_name is mandatory — enforced at field level but double-checked here."""
		if not self.career_name:
			frappe.throw(_("Career Name is mandatory."), frappe.ValidationError)

	def _validate_salary_range(self):
		"""minimum_salary must not exceed maximum_salary."""
		if self.minimum_salary and self.maximum_salary:
			if self.minimum_salary > self.maximum_salary:
				frappe.throw(
					_(
						"Minimum Salary ({0}) cannot exceed Maximum Salary ({1}).".format(
							frappe.format_value(self.minimum_salary, {"fieldtype": "Currency"}),
							frappe.format_value(self.maximum_salary, {"fieldtype": "Currency"}),
						)
					),
					frappe.ValidationError,
				)

	def _set_defaults(self):
		"""Ensure programmatic defaults are applied on every save."""
		if not self.knowledge_version:
			self.knowledge_version = 1

		if self.active is None:
			self.active = 1

		if not self.currency:
			self.currency = "INR"
