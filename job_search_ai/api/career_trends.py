import frappe
from job_search_ai.services.career_trend_service import CareerTrendService

@frappe.whitelist(allow_guest=True)
def get_career_trends(degree, branch, year, country, interests=None, skills=None):
	"""
	Whitelisted API method to analyze and recommend career trends based on a student profile.
	"""
	return CareerTrendService.get_trends(
		degree=degree,
		branch=branch,
		year=year,
		country=country,
		interests=interests,
		skills=skills
	)
