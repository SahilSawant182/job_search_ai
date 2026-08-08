// Copyright (c) 2026, Sahil Sawant and contributors
// For license information, please see license.txt

// frappe.ui.form.on("Job Description", {
// 	refresh(frm) {

// 	},
// });


frappe.ui.form.on('Job Description', {
    job_profile: function (frm) {
        if (!frm.doc.job_profile) return;

        // Get the actual career name from the linked Career Knowledge doc
        frappe.db.get_value('Career Knowledge', frm.doc.job_profile, 'career_name')
            .then((r) => {
                let role_name = (r.message && r.message.career_name) || frm.doc.job_profile;

                frappe.call({
                    method: "job_search_ai.agents.skill_agent.api.generate_skills", // replace with actual dotted path
                    args: {
                        role: role_name,
                        save: 0   // don't create a new Job Description, just fetch data
                    },
                    freeze: true,
                    freeze_message: __("Generating skills for {0}...", [role_name]),
                    callback: function (res) {
                        if (res.exc || !res.message) return;
                        let data = res.message;

                        frm.set_value('role', data.role);
                        frm.set_value('foundation_skills', (data.foundation_skills || []).join(', '));
                        frm.set_value('core_domain_skills', (data.core_domain_skills || []).join(', '));
                        frm.set_value('industry_skills', (data.industry_skills || []).join(', '));
                        frm.set_value('emerging_skills', (data.emerging_skills || []).join(', '));
                    },
                    error: function () {
                        frappe.msgprint({
                            title: __('Error'),
                            message: __('Failed to generate skills. Please try again.'),
                            indicator: 'red'
                        });
                    }
                });
            });
    }
});