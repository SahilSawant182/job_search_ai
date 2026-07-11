import os
import frappe
from frappe import _

class ConfigurationError(Exception):
	"""Raised when a required configuration is missing or invalid."""
	pass

class SettingsService:
	_instance = None

	def __init__(self):
		self._doc = None
		try:
			# Try to load the document using frappe.get_cached_doc()
			if frappe.local and getattr(frappe.local, "initialised", False):
				self._doc = frappe.get_cached_doc("Job Search AI Settings")
		except Exception:
			# In some test/offline environments, the DocType might not be loaded/created yet
			self._doc = None

	@classmethod
	def get(cls):
		# Always recreate or update reference if we are in testing to prevent stale caching
		if cls._instance is None:
			cls._instance = cls()
		else:
			# Update the internal document reference in case it has changed or loaded since initialization
			try:
				if frappe.local and getattr(frappe.local, "initialised", False):
					cls._instance._doc = frappe.get_cached_doc("Job Search AI Settings")
			except Exception:
				pass
		return cls._instance

	def _get_value(self, fieldname, env_var, default_val=None):
		# 1. Preferred: DocType settings
		if self._doc:
			try:
				val = self._doc.get(fieldname)
				if val is not None and val != "":
					if isinstance(default_val, bool):
						return bool(val)
					if isinstance(default_val, int):
						try:
							return int(val)
						except (ValueError, TypeError):
							pass
					return val
			except Exception:
				pass

		# 2. Fallback: Environment Variables
		env_val = os.environ.get(env_var)
		if env_val is not None and env_val != "":
			if isinstance(default_val, bool):
				return env_val.lower() in ("true", "1", "yes")
			if isinstance(default_val, int):
				try:
					return int(env_val)
				except (ValueError, TypeError):
					pass
			return env_val

		# 3. Last fallback: Hardcoded Defaults
		return default_val

	@property
	def ollama_endpoint(self):
		val = self._get_value("ollama_endpoint", "OLLAMA_ENDPOINT", "http://135.181.6.215:11434/api/generate")
		if not val:
			raise ConfigurationError(_("Ollama Endpoint is not configured. Please set it in Job Search AI Settings or the OLLAMA_ENDPOINT environment variable."))
		return val

	@property
	def default_llm_model(self):
		return self._get_value("default_llm_model", "LLM_MODEL_NAME", "qwen2.5:1.5b")

	@property
	def llm_timeout_seconds(self):
		return self._get_value("llm_timeout_seconds", "LLM_TIMEOUT", 180)

	@property
	def retry_count(self):
		return self._get_value("retry_count", "LLM_RETRY_COUNT", 1)

	@property
	def maximum_search_results_per_query(self):
		return self._get_value("maximum_search_results_per_query", "TAVILY_MAX_RESULTS", 3)

	@property
	def parallel_search_workers(self):
		return self._get_value("parallel_search_workers", "TAVILY_PARALLEL_WORKERS", 4)

	@property
	def maximum_results_sent_to_llm(self):
		return self._get_value("maximum_results_sent_to_llm", "MAX_RESULTS_SENT_TO_LLM", 6)

	@property
	def maximum_prompt_characters(self):
		return self._get_value("maximum_prompt_characters", "MAX_PROMPT_CHARACTERS", 4000)

	@property
	def enable_debug_logging(self):
		return self._get_value("enable_debug_logging", "ENABLE_DEBUG_LOGGING", False)

	@property
	def enable_benchmark_mode(self):
		return self._get_value("enable_benchmark_mode", "ENABLE_BENCHMARK_MODE", False)

	def get_password(self, fieldname):
		# 1. Preferred: DocType settings
		if self._doc:
			try:
				val = self._doc.get_password(fieldname, raise_exception=False)
				if val is not None and val != "":
					return val
			except Exception:
				pass

		# 2. Fallback: Environment Variables
		env_var = fieldname.upper()
		env_val = os.environ.get(env_var)
		if env_val is not None and env_val != "":
			return env_val

		# If the Tavily API Key is missing, raise a clear exception
		if fieldname == "tavily_api_key":
			raise ConfigurationError(_("Tavily API Key is not configured. Please set it in Job Search AI Settings or the TAVILY_API_KEY environment variable."))

		return None
