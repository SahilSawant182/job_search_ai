import json
import frappe
from frappe import _
from job_search_ai.services.settings_service import SettingsService, ConfigurationError
from job_search_ai.agents.career_trend import CareerTrendAgent
from job_search_ai.agents.career_trend.schemas import StudentProfile

class CareerTrendService:
	"""
	Service layer to handle validation, settings verification, profile initialization,
	and CareerTrendAgent execution.
	"""

	@staticmethod
	def get_trends(degree, branch, year, country, interests=None, skills=None):
		# 1. Validate Job Search AI Settings
		try:
			settings = SettingsService.get()
			# Try to fetch required settings
			tavily_key = settings.get_password("tavily_api_key")
			ollama_endpoint = settings.ollama_endpoint
			default_model = settings.default_llm_model

			if not tavily_key or not ollama_endpoint or not default_model:
				frappe.throw(
					_("Please configure Job Search AI Settings before using Career Trend Agent."),
					frappe.ValidationError
				)
		except ConfigurationError:
			frappe.throw(
				_("Please configure Job Search AI Settings before using Career Trend Agent."),
				frappe.ValidationError
			)

		# 2. Validate input parameters
		if not degree or not str(degree).strip():
			frappe.throw(_("Degree is required."), frappe.ValidationError)
		if not branch or not str(branch).strip():
			frappe.throw(_("Branch is required."), frappe.ValidationError)
		if not year:
			frappe.throw(_("Academic Year is required."), frappe.ValidationError)
		if not country or not str(country).strip():
			frappe.throw(_("Country is required."), frappe.ValidationError)

		try:
			year_int = int(year)
		except (ValueError, TypeError):
			frappe.throw(_("Academic Year must be an integer."), frappe.ValidationError)

		# 3. Parse list-like parameters (interests and skills)
		parsed_interests = CareerTrendService._parse_list_input(interests)
		parsed_skills = CareerTrendService._parse_list_input(skills)

		# 4. Initialize StudentProfile
		student = StudentProfile(
			degree=str(degree).strip(),
			branch=str(branch).strip(),
			year=year_int,
			country=str(country).strip(),
			interests=parsed_interests,
			skills=parsed_skills,
		)

		# 5. Run the CareerTrendAgent
		try:
			agent = CareerTrendAgent()
			response = agent.run(student)
			
			res_dict = response.to_dict()
			metrics = getattr(response, "metrics", {})
			res_dict["metadata"] = {
				"total_execution_time_seconds": metrics.get("total_execution_time", 0.0),
				"search_execution_time_seconds": metrics.get("parallel_search_time", 0.0),
				"llm_execution_time_seconds": metrics.get("llm_response_time", 0.0),
				"prompt_length_characters": metrics.get("prompt_length", 0),
				"search_results_used": metrics.get("filtered_results_count", 0),
				"model": metrics.get("model_name", "qwen2.5:1.5b"),
				"knowledge_hit": metrics.get("knowledge_hit", False),
				"avg_similarity_score": metrics.get("avg_similarity_score", 0.0),
				"knowledge_count": metrics.get("knowledge_count", 0),
				"tavily_used": metrics.get("tavily_used", True)
			}
			return res_dict
		except Exception as exc:
			frappe.log_error(f"CareerTrendAgent execution failed: {exc}", "Career Trend Service Error")
			frappe.throw(
				_("An error occurred during career trend analysis: {0}").format(str(exc)),
				frappe.ValidationError
			)

	@staticmethod
	def _parse_list_input(value):
		if not value:
			return []
		if isinstance(value, list):
			return [v.strip() for v in value if v and str(v).strip()]
		if isinstance(value, str):
			value = value.strip()
			if value.startswith("[") and value.endswith("]"):
				try:
					parsed = json.loads(value)
					if isinstance(parsed, list):
						return [str(v).strip() for v in parsed if v and str(v).strip()]
				except Exception:
					pass
			# Fallback to comma-separated list
			return [v.strip() for v in value.split(",") if v and v.strip()]
		return []
