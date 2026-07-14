// Copyright (c) 2026, Sahil Sawant and contributors
// For license information, please see license.txt

frappe.ui.form.on("Career Knowledge", {
	refresh(frm) {
		// Highlight active status in the form header
		if (!frm.doc.active) {
			frm.dashboard.set_headline_alert(
				'<span class="text-danger">&#9679; This Career Knowledge record is inactive.</span>'
			);
		}
	},

	before_save(frm) {
		// Client-side salary range guard (server also validates)
		if (frm.doc.minimum_salary && frm.doc.maximum_salary) {
			if (frm.doc.minimum_salary > frm.doc.maximum_salary) {
				frappe.msgprint({
					title: __("Validation Error"),
					indicator: "red",
					message: __(
						"Minimum Salary cannot exceed Maximum Salary."
					),
				});
				frappe.validated = false;
			}
		}
	},

	career_name(frm) {
		if (!frm.doc.career_name) {
			frappe.msgprint({
				title: __("Required"),
				indicator: "orange",
				message: __("Career Name is mandatory."),
			});
		}
	},
});
