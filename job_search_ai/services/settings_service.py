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
	def llm_provider(self):
		return self._get_value("llm_provider", "LLM_PROVIDER", "ollama")

	@property
	def omniroute_base_url(self):
		return self._get_value("omniroute_base_url", "OMNIROUTE_BASE_URL", "http://localhost:20128/v1")

	@property
	def omniroute_model(self):
		return self._get_value("omniroute_model", "OMNIROUTE_MODEL", "career-agent")

	@property
	def ollama_endpoint(self):
		val = self._get_value("ollama_endpoint", "OLLAMA_ENDPOINT", "http://135.181.6.215:11434/api/generate")
		if not val:
			raise ConfigurationError(_("Ollama Endpoint is not configured. Please set it in Job Search AI Settings or the OLLAMA_ENDPOINT environment variable."))
		return val


	@property
	def ollama_base_url(self) -> str:
		"""Derive the Ollama server base URL (scheme + host + port) from ollama_endpoint.

		ollama_endpoint stores the full path used by the LLM service, e.g.
		  http://135.181.6.215:11434/api/generate
		EmbeddingService needs the root, e.g.
		  http://135.181.6.215:11434
		This property strips the path component so callers can append their own path.
		"""
		import urllib.parse
		parsed = urllib.parse.urlparse(self.ollama_endpoint)
		return f"{parsed.scheme}://{parsed.netloc}"

	@property
	def embedding_model(self) -> str:
		"""Name of the Ollama model used to generate text embeddings."""
		return self._get_value("embedding_model", "EMBEDDING_MODEL", "nomic-embed-text")

	@property
	def embedding_timeout_seconds(self) -> int:
		"""Timeout in seconds for embedding HTTP requests (falls back to llm_timeout_seconds)."""
		return self._get_value("embedding_timeout_seconds", "EMBEDDING_TIMEOUT", self.llm_timeout_seconds)

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

	# ------------------------------------------------------------------
	# Vector Database (Qdrant)
	# ------------------------------------------------------------------

	@property
	def qdrant_url(self) -> str:
		"""Base URL of the Qdrant server (e.g. http://localhost:6333)."""
		val = self._get_value("qdrant_url", "QDRANT_URL", "http://localhost:6333")
		if not val or not str(val).strip():
			raise ConfigurationError(
				_("Qdrant URL is not configured. Please set it in Job Search AI Settings or the QDRANT_URL environment variable.")
			)
		return str(val).rstrip("/")

	@property
	def qdrant_collection_name(self) -> str:
		"""Default Qdrant collection used for career intelligence vectors."""
		val = self._get_value("qdrant_collection_name", "QDRANT_COLLECTION_NAME", "career_knowledge")
		if not val or not str(val).strip():
			raise ConfigurationError(
				_("Qdrant Collection Name is not configured. Please set it in Job Search AI Settings or the QDRANT_COLLECTION_NAME environment variable.")
			)
		return str(val).strip()

	@property
	def embedding_dimension(self) -> int:
		"""Dimension of vectors produced by the configured embedding model."""
		val = self._get_value("embedding_dimension", "EMBEDDING_DIMENSION", 768)
		try:
			dim = int(val)
		except (ValueError, TypeError):
			raise ConfigurationError(
				_("Embedding Dimension must be a positive integer. Got: {0}").format(val)
			)
		if dim <= 0:
			raise ConfigurationError(
				_("Embedding Dimension must be greater than 0. Got: {0}").format(dim)
			)
		return dim

	@property
	def vector_distance(self) -> str:
		"""Distance metric used when creating Qdrant collections.

		Valid values: Cosine, Dot, Euclid
		"""
		_VALID = {"Cosine", "Dot", "Euclid"}
		val = self._get_value("vector_distance", "VECTOR_DISTANCE", "Cosine")
		if not val or str(val).strip() not in _VALID:
			raise ConfigurationError(
				_("Similarity Metric must be one of {0}. Got: {1}").format(
					", ".join(sorted(_VALID)), val
				)
			)
		return str(val).strip()

	# ------------------------------------------------------------------
	# Knowledge Retrieval
	# ------------------------------------------------------------------

	@property
	def similarity_threshold(self) -> float:
		"""Minimum cosine similarity score (0.0–1.0) for a vector result to be included."""
		val = self._get_value("similarity_threshold", "SIMILARITY_THRESHOLD", 0.75)
		try:
			f = float(val)
		except (ValueError, TypeError):
			raise ConfigurationError(
				_("Similarity Threshold must be a float between 0.0 and 1.0. Got: {0}").format(val)
			)
		if not (0.0 <= f <= 1.0):
			raise ConfigurationError(
				_("Similarity Threshold must be between 0.0 and 1.0. Got: {0}").format(f)
			)
		return f

	# ------------------------------------------------------------------
	# Skill Embedding Index
	# ------------------------------------------------------------------

	@property
	def skill_embedding_collection_name(self) -> str:
		val = self._get_value("skill_embedding_collection_name", "SKILL_EMBEDDING_COLLECTION", "skill_embeddings")
		return str(val or "skill_embeddings").strip()

	@property
	def skill_match_top_k(self) -> int:
		val = self._get_value("skill_match_top_k", "SKILL_MATCH_TOP_K", 5)
		try:
			n = int(val)
		except (ValueError, TypeError):
			n = 5
		return n if n > 0 else 5

	@property
	def skill_match_auto_threshold(self) -> float:
		return self._get_float_between_zero_and_one("skill_match_auto_threshold", "SKILL_MATCH_AUTO_THRESHOLD", 0.90)

	@property
	def skill_match_uncertain_threshold(self) -> float:
		return self._get_float_between_zero_and_one("skill_match_uncertain_threshold", "SKILL_MATCH_UNCERTAIN_THRESHOLD", 0.75)

	@property
	def skill_match_confidence_gap(self) -> float:
		return self._get_float_between_zero_and_one("skill_match_confidence_gap", "SKILL_MATCH_CONFIDENCE_GAP", 0.05)

	@property
	def skill_embedding_version(self) -> str:
		val = self._get_value("skill_embedding_version", "SKILL_EMBEDDING_VERSION", "skill-v1")
		return str(val or "skill-v1").strip()

	def _get_float_between_zero_and_one(self, fieldname: str, env_var: str, default_val: float) -> float:
		val = self._get_value(fieldname, env_var, default_val)
		try:
			f = float(val)
		except (ValueError, TypeError):
			return default_val
		return f if 0.0 <= f <= 1.0 else default_val

	@property
	def max_retrieved_knowledge(self) -> int:
		"""Maximum number of Career Knowledge records returned per retrieval query."""
		val = self._get_value("max_retrieved_knowledge", "MAX_RETRIEVED_KNOWLEDGE", 5)
		try:
			n = int(val)
		except (ValueError, TypeError):
			raise ConfigurationError(
				_("Maximum Retrieved Knowledge must be a positive integer. Got: {0}").format(val)
			)
		if n <= 0:
			raise ConfigurationError(
				_("Maximum Retrieved Knowledge must be greater than 0. Got: {0}").format(n)
			)
		return n

	@property
	def minimum_knowledge_results(self) -> int:
		"""Minimum number of retrieved Knowledge records needed to skip the Tavily web search."""
		val = self._get_value("minimum_knowledge_results", "MINIMUM_KNOWLEDGE_RESULTS", 3)
		try:
			n = int(val)
		except (ValueError, TypeError):
			raise ConfigurationError(
				_("Minimum Knowledge Results must be a positive integer. Got: {0}").format(val)
			)
		if n <= 0:
			raise ConfigurationError(
				_("Minimum Knowledge Results must be greater than 0. Got: {0}").format(n)
			)
		return n

	@property
	def refresh_batch_size(self) -> int:
		"""Number of records processed in a single database batch."""
		val = self._get_value("refresh_batch_size", "REFRESH_BATCH_SIZE", 20)
		try:
			n = int(val)
		except (ValueError, TypeError):
			raise ConfigurationError(
				_("Refresh Batch Size must be a positive integer. Got: {0}").format(val)
			)
		if n <= 0:
			raise ConfigurationError(
				_("Refresh Batch Size must be greater than 0. Got: {0}").format(n)
			)
		return n

	@property
	def maximum_refresh_per_run(self) -> int:
		"""Maximum number of records refreshed in a single execution run."""
		val = self._get_value("maximum_refresh_per_run", "MAXIMUM_REFRESH_PER_RUN", 100)
		try:
			n = int(val)
		except (ValueError, TypeError):
			raise ConfigurationError(
				_("Maximum Refresh Per Run must be a positive integer. Got: {0}").format(val)
			)
		if n <= 0:
			raise ConfigurationError(
				_("Maximum Refresh Per Run must be greater than 0. Got: {0}").format(n)
			)
		return n

	@property
	def enable_automatic_refresh(self) -> bool:
		"""Whether automatic knowledge refresh is enabled."""
		val = self._get_value("enable_automatic_refresh", "ENABLE_AUTOMATIC_REFRESH", 1)
		if str(val).lower() in ("true", "1", "yes", "on"):
			return True
		if str(val).lower() in ("false", "0", "no", "off"):
			return False
		return bool(val)


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
