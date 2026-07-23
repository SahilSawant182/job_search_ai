"""
Persistent skill embedding infrastructure for semantic skill matching.

Skill Master remains the source of truth. Qdrant is only a searchable semantic
projection of active canonical Skill Master records.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional, Protocol, Sequence

from job_search_ai.services.skill_gap.normalizer import get_skill_key, normalize_skill

logger = logging.getLogger(__name__)

EmbeddingProvider = Callable[[str], List[float]]
LLMEquivalenceDecider = Callable[[str, str], bool]


@dataclass(frozen=True)
class SkillIndexConfig:
    """Runtime configuration for the persistent skill embedding index."""

    collection_name: str = "skill_embeddings"
    top_k: int = 5
    auto_match_threshold: float = 0.90
    uncertain_threshold: float = 0.75
    confidence_gap_threshold: float = 0.05
    embedding_version: str = "skill-v1"

    @classmethod
    def from_settings(cls, settings: Any | None = None) -> "SkillIndexConfig":
        if settings is None:
            try:
                from job_search_ai.services.settings_service import SettingsService

                settings = SettingsService.get()
            except Exception:
                settings = None

        return cls(
            collection_name=_get_config_value(
                settings,
                "skill_embedding_collection_name",
                "SKILL_EMBEDDING_COLLECTION",
                cls.collection_name,
            ),
            top_k=_as_int(_get_config_value(settings, "skill_match_top_k", "SKILL_MATCH_TOP_K", cls.top_k), cls.top_k),
            auto_match_threshold=_as_float(
                _get_config_value(settings, "skill_match_auto_threshold", "SKILL_MATCH_AUTO_THRESHOLD", cls.auto_match_threshold),
                cls.auto_match_threshold,
            ),
            uncertain_threshold=_as_float(
                _get_config_value(settings, "skill_match_uncertain_threshold", "SKILL_MATCH_UNCERTAIN_THRESHOLD", cls.uncertain_threshold),
                cls.uncertain_threshold,
            ),
            confidence_gap_threshold=_as_float(
                _get_config_value(settings, "skill_match_confidence_gap", "SKILL_MATCH_CONFIDENCE_GAP", cls.confidence_gap_threshold),
                cls.confidence_gap_threshold,
            ),
            embedding_version=_get_config_value(
                settings,
                "skill_embedding_version",
                "SKILL_EMBEDDING_VERSION",
                cls.embedding_version,
            ),
        )


@dataclass(frozen=True)
class SkillMasterRecord:
    """Canonical Skill Master data required by the semantic index."""

    skill_id: str
    skill_name: str
    normalized_key: str
    aliases: List[str] = field(default_factory=list)
    category: str = ""
    domain: str = ""
    active: bool = True
    description: str = ""
    modified: str = ""


@dataclass(frozen=True)
class SkillSearchCandidate:
    """Candidate returned by the persistent skill embedding index."""

    skill_id: str
    skill_name: str
    normalized_key: str
    score: float
    aliases: List[str] = field(default_factory=list)
    category: str = ""
    domain: str = ""
    active: bool = True
    embedding_model: str = ""
    embedding_version: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SkillResolution:
    """Resolution decision for one raw input skill."""

    input_skill: str
    normalized_skill: str
    canonical_skill: Optional[str]
    stage: str
    confidence_band: str
    score: float = 0.0
    accepted: bool = False
    fallback_reason: str = ""
    candidates: List[SkillSearchCandidate] = field(default_factory=list)


class VectorIndexProtocol(Protocol):
    def create_collection(self, *, recreate: bool = False) -> bool: ...
    def upsert(self, id: str | int, vector: list[float], payload: dict[str, Any] | None = None) -> None: ...
    def delete(self, id: str | int) -> None: ...
    def search(self, query_vector: list[float], limit: int = 10, score_threshold: float | None = None) -> list[Any]: ...


class SkillMasterRepository:
    """Read canonical skills and aliases from Skill Master when Frappe is available."""

    def get_active_skills(self) -> List[SkillMasterRecord]:
        frappe = _get_frappe()
        if frappe is None or not _doctype_exists(frappe, "Skill Master"):
            return []

        rows = frappe.get_all(
            "Skill Master",
            filters={"active": 1},
            fields=["name", "skill_name", "category", "domain", "active", "description", "modified"],
        )
        return [self._record_from_row(frappe, row) for row in rows]

    def get_skill(self, skill_id: str) -> Optional[SkillMasterRecord]:
        frappe = _get_frappe()
        if frappe is None or not skill_id or not frappe.db.exists("Skill Master", skill_id):
            return None
        doc = frappe.get_doc("Skill Master", skill_id)
        return self._record_from_doc(doc)

    def find_active_by_key(self, skill_name: str) -> Optional[SkillMasterRecord]:
        key = get_skill_key(skill_name)
        if not key:
            return None
        for record in self.get_active_skills():
            if record.normalized_key == key:
                return record
            if any(get_skill_key(alias) == key for alias in record.aliases):
                return record
        return None

    def _record_from_row(self, frappe: Any, row: Any) -> SkillMasterRecord:
        doc = frappe.get_doc("Skill Master", row.get("name"))
        return self._record_from_doc(doc)

    def _record_from_doc(self, doc: Any) -> SkillMasterRecord:
        aliases = []
        for alias_row in getattr(doc, "aliases", []) or []:
            if isinstance(alias_row, dict):
                alias = alias_row.get("alias")
            else:
                alias = getattr(alias_row, "alias", None)
            if alias:
                aliases.append(str(alias))

        skill_name = str(getattr(doc, "skill_name", "") or getattr(doc, "name", ""))
        return SkillMasterRecord(
            skill_id=str(getattr(doc, "name", skill_name)),
            skill_name=skill_name,
            normalized_key=get_skill_key(skill_name),
            aliases=aliases,
            category=str(getattr(doc, "category", "") or ""),
            domain=str(getattr(doc, "domain", "") or ""),
            active=bool(getattr(doc, "active", True)),
            description=str(getattr(doc, "description", "") or ""),
            modified=str(getattr(doc, "modified", "") or ""),
        )


class PersistentSkillEmbeddingCache:
    """Persistent embedding cache backed by Frappe when available, with test fallback."""

    DOCTYPE = "Skill Embedding Cache"

    def __init__(self, memory_store: Optional[Dict[str, Dict[str, Any]]] = None) -> None:
        self._memory_store = memory_store if memory_store is not None else {}

    def get(self, cache_key: str, model: str, version: str, text_hash: str) -> Optional[List[float]]:
        row = self._get_row(cache_key)
        if not row:
            return None
        if row.get("embedding_model") != model or row.get("embedding_version") != version:
            return None
        if row.get("text_hash") != text_hash:
            return None
        try:
            vector = json.loads(row.get("embedding_json") or "[]")
        except (TypeError, ValueError):
            return None
        if isinstance(vector, list) and all(isinstance(v, (int, float)) for v in vector):
            logger.info("SkillEmbeddingCache: hit key=%s model=%s version=%s", cache_key, model, version)
            return vector
        return None

    def set(
        self,
        cache_key: str,
        skill_text: str,
        vector: Sequence[float],
        model: str,
        version: str,
        text_hash: str,
        source: str = "runtime",
    ) -> None:
        payload = {
            "skill_key": cache_key,
            "skill_text": skill_text,
            "embedding_json": json.dumps(list(vector)),
            "embedding_model": model,
            "embedding_version": version,
            "text_hash": text_hash,
            "source": source,
            "last_updated": _utc_now(),
        }
        frappe = _get_frappe()
        if frappe is not None and _doctype_exists(frappe, self.DOCTYPE):
            existing = frappe.db.get_value(self.DOCTYPE, {"skill_key": cache_key}, "name")
            if existing:
                doc = frappe.get_doc(self.DOCTYPE, existing)
                for key, value in payload.items():
                    setattr(doc, key, value)
                doc.save(ignore_permissions=True)
            else:
                try:
                    doc = frappe.get_doc({"doctype": self.DOCTYPE, **payload})
                    doc.insert(ignore_permissions=True)
                except frappe.DuplicateEntryError:
                    existing = frappe.db.get_value(self.DOCTYPE, {"skill_key": cache_key}, "name")
                    if existing:
                        doc = frappe.get_doc(self.DOCTYPE, existing)
                        for key, value in payload.items():
                            setattr(doc, key, value)
                        doc.save(ignore_permissions=True)
        else:
            self._memory_store[cache_key] = payload
        logger.info("SkillEmbeddingCache: stored key=%s model=%s version=%s source=%s", cache_key, model, version, source)

    def invalidate(self, cache_key: str) -> None:
        frappe = _get_frappe()
        if frappe is not None and _doctype_exists(frappe, self.DOCTYPE):
            existing = frappe.db.get_value(self.DOCTYPE, {"skill_key": cache_key}, "name")
            if existing:
                frappe.delete_doc(self.DOCTYPE, existing, ignore_permissions=True)
        self._memory_store.pop(cache_key, None)
        logger.info("SkillEmbeddingCache: invalidated key=%s", cache_key)

    def _get_row(self, cache_key: str) -> Optional[Dict[str, Any]]:
        frappe = _get_frappe()
        if frappe is not None and _doctype_exists(frappe, self.DOCTYPE):
            rows = frappe.get_all(
                self.DOCTYPE,
                filters={"skill_key": cache_key},
                fields=["skill_key", "skill_text", "embedding_json", "embedding_model", "embedding_version", "text_hash"],
                limit=1,
            )
            return rows[0] if rows else None
        return self._memory_store.get(cache_key)


class SkillEmbeddingIndex:
    """Qdrant-backed semantic index for canonical Skill Master records."""

    def __init__(self, vector_index: Optional[VectorIndexProtocol] = None, config: Optional[SkillIndexConfig] = None) -> None:
        self.config = config or SkillIndexConfig.from_settings()
        if vector_index is None:
            from job_search_ai.services.ai.vector_index import VectorIndex

            vector_index = VectorIndex(collection_name=self.config.collection_name)
        self.vector_index = vector_index

    def ensure_collection(self, recreate: bool = False) -> bool:
        return self.vector_index.create_collection(recreate=recreate)

    def upsert_skill(self, record: SkillMasterRecord, vector: Sequence[float], embedding_text: str, model: str, version: str) -> None:
        payload = {
            "skill_master_id": record.skill_id,
            "skill_name": record.skill_name,
            "normalized_key": record.normalized_key,
            "aliases": record.aliases,
            "category": record.category,
            "domain": record.domain,
            "active": record.active,
            "embedding_model": model,
            "embedding_version": version,
            "embedding_text_hash": _hash_text(embedding_text),
            "synced_at": _utc_now(),
        }
        self.vector_index.upsert(id=record.skill_id, vector=list(vector), payload=payload)
        logger.info("SkillEmbeddingIndex: upserted skill=%s key=%s", record.skill_name, record.normalized_key)

    def delete_skill(self, skill_id: str) -> None:
        self.vector_index.delete(skill_id)
        logger.info("SkillEmbeddingIndex: deleted skill_id=%s", skill_id)

    def search(self, vector: Sequence[float], top_k: Optional[int] = None) -> List[SkillSearchCandidate]:
        hits = self.vector_index.search(query_vector=list(vector), limit=top_k or self.config.top_k)
        candidates: List[SkillSearchCandidate] = []
        for hit in hits:
            payload = dict(getattr(hit, "payload", {}) or {})
            candidates.append(
                SkillSearchCandidate(
                    skill_id=str(payload.get("skill_master_id") or getattr(hit, "id", "")),
                    skill_name=str(payload.get("skill_name") or ""),
                    normalized_key=str(payload.get("normalized_key") or ""),
                    aliases=list(payload.get("aliases") or []),
                    category=str(payload.get("category") or ""),
                    domain=str(payload.get("domain") or ""),                        
                    active=bool(payload.get("active", True)),
                    embedding_model=str(payload.get("embedding_model") or ""),
                    embedding_version=str(payload.get("embedding_version") or ""),
                    score=float(getattr(hit, "score", 0.0) or 0.0),
                    payload=payload,
                )
            )
        return candidates


class SkillEmbeddingBuilder:
    """Build and synchronize rich Skill Master embeddings into Qdrant."""

    def __init__(
        self,
        embedding_provider: Optional[EmbeddingProvider] = None,
        cache: Optional[PersistentSkillEmbeddingCache] = None,
        index: Optional[SkillEmbeddingIndex] = None,
        repository: Optional[SkillMasterRepository] = None,
        config: Optional[SkillIndexConfig] = None,
        embedding_model: Optional[str] = None,
    ) -> None:
        self.config = config or SkillIndexConfig.from_settings()
        self.embedding_provider = embedding_provider or _default_embedding_provider()
        self.cache = cache or PersistentSkillEmbeddingCache()
        self.index = index or SkillEmbeddingIndex(config=self.config)
        self.repository = repository or SkillMasterRepository()
        self.embedding_model = embedding_model or _default_embedding_model()

    def rebuild_all(self, recreate_collection: bool = False) -> int:
        self.index.ensure_collection(recreate=recreate_collection)
        count = 0
        for record in self.repository.get_active_skills():
            self.sync_record(record)
            count += 1
        logger.info("SkillEmbeddingBuilder: rebuilt %d skill embedding(s)", count)
        return count

    def sync_skill(self, skill_id: str) -> bool:
        record = self.repository.get_skill(skill_id)
        if record is None:
            logger.warning("SkillEmbeddingBuilder: skill_id=%s not found", skill_id)
            return False
        if not record.active:
            self.delete_skill(record.skill_id)
            return False
        self.sync_record(record)
        return True

    def sync_record(self, record: SkillMasterRecord) -> None:
        self.index.ensure_collection(recreate=False)
        embedding_text = build_skill_embedding_text(record)
        text_hash = _hash_text(embedding_text)
        cache_key = _cache_key(record.normalized_key)
        vector = self.cache.get(cache_key, self.embedding_model, self.config.embedding_version, text_hash)
        if vector is None:
            vector = self.embedding_provider(embedding_text)
            self.cache.set(
                cache_key=cache_key,
                skill_text=embedding_text,
                vector=vector,
                model=self.embedding_model,
                version=self.config.embedding_version,
                text_hash=text_hash,
                source="skill_master",
            )
        self.index.upsert_skill(record, vector, embedding_text, self.embedding_model, self.config.embedding_version)

    def delete_skill(self, skill_id: str) -> None:
        record = self.repository.get_skill(skill_id)
        cache_key = _cache_key(record.normalized_key if record else get_skill_key(skill_id))
        self.cache.invalidate(cache_key)
        self.index.delete_skill(skill_id)


class SkillEmbeddingResolver:
    """Resolve one input skill to a canonical Skill Master skill via cache + Qdrant."""

    def __init__(
        self,
        embedding_provider: Optional[EmbeddingProvider] = None,
        cache: Optional[PersistentSkillEmbeddingCache] = None,
        index: Optional[SkillEmbeddingIndex] = None,
        repository: Optional[SkillMasterRepository] = None,
        config: Optional[SkillIndexConfig] = None,
        embedding_model: Optional[str] = None,
    ) -> None:
        self.config = config or SkillIndexConfig.from_settings()
        self.embedding_provider = embedding_provider or _default_embedding_provider()
        self.cache = cache or PersistentSkillEmbeddingCache()
        self.index = index or SkillEmbeddingIndex(config=self.config)
        self.repository = repository or SkillMasterRepository()
        self.embedding_model = embedding_model or _default_embedding_model()

    def resolve(
        self,
        skill: str,
        *,
        domain: str = "",
        category: str = "",
        llm_decider: Optional[LLMEquivalenceDecider] = None,
    ) -> SkillResolution:
        normalized_skill = normalize_skill(skill)
        exact_record = self.repository.find_active_by_key(normalized_skill)
        if exact_record:
            logger.info(
                "SkillEmbeddingResolver: stage=skill_master_exact input=%r canonical=%r",
                skill,
                exact_record.skill_name,
            )
            return SkillResolution(skill, normalized_skill, exact_record.skill_name, "skill_master_exact", "exact", 1.0, True)

        vector = self._get_or_create_runtime_embedding(normalized_skill)
        candidates = self.index.search(vector, top_k=self.config.top_k)
        decision = self._validate_candidates(skill, normalized_skill, candidates, domain=domain, category=category)

        if decision.accepted:
            return decision

        if decision.confidence_band == "uncertain" and candidates and llm_decider is not None:
            top = candidates[0]
            try:
                if llm_decider(normalized_skill, top.skill_name):
                    logger.info(
                        "SkillEmbeddingResolver: stage=llm_fallback input=%r canonical=%r score=%.4f",
                        skill,
                        top.skill_name,
                        top.score,
                    )
                    return SkillResolution(
                        skill,
                        normalized_skill,
                        top.skill_name,
                        "llm_fallback",
                        "uncertain",
                        top.score,
                        True,
                        candidates=candidates,
                    )
            except Exception as exc:
                logger.warning("SkillEmbeddingResolver: llm fallback failed input=%r error=%s", skill, exc)

        self.queue_candidate(skill, normalized_skill, decision.fallback_reason, candidates)
        return decision

    def queue_candidate(
        self,
        raw_skill: str,
        normalized_skill: str,
        reason: str,
        candidates: Sequence[SkillSearchCandidate],
    ) -> None:
        frappe = _get_frappe()
        payload_candidates = [
            {"skill_name": c.skill_name, "score": c.score, "skill_master_id": c.skill_id}
            for c in candidates[: self.config.top_k]
        ]
        if frappe is not None and _doctype_exists(frappe, "Skill Candidate"):
            existing = frappe.db.get_value("Skill Candidate", {"normalized_key": get_skill_key(normalized_skill), "status": "Pending Review"}, "name")
            if existing:
                doc = frappe.get_doc("Skill Candidate", existing)
                doc.last_seen = _utc_now()
                doc.occurrence_count = int(getattr(doc, "occurrence_count", 0) or 0) + 1
                doc.fallback_reason = reason
                doc.top_candidates_json = json.dumps(payload_candidates)
                doc.save(ignore_permissions=True)
            else:
                doc = frappe.get_doc({
                    "doctype": "Skill Candidate",
                    "skill_name": raw_skill,
                    "normalized_skill": normalized_skill,
                    "normalized_key": get_skill_key(normalized_skill),
                    "status": "Pending Review",
                    "fallback_reason": reason,
                    "top_candidates_json": json.dumps(payload_candidates),
                    "occurrence_count": 1,
                    "first_seen": _utc_now(),
                    "last_seen": _utc_now(),
                })
                doc.insert(ignore_permissions=True)
            frappe.db.commit()
        logger.info(
            "SkillEmbeddingResolver: stage=unknown_candidate input=%r reason=%s candidates=%s",
            raw_skill,
            reason,
            payload_candidates,
        )

    def _get_or_create_runtime_embedding(self, normalized_skill: str) -> List[float]:
        embedding_text = build_runtime_skill_embedding_text(normalized_skill)
        text_hash = _hash_text(embedding_text)
        cache_key = _cache_key(get_skill_key(normalized_skill))
        vector = self.cache.get(cache_key, self.embedding_model, self.config.embedding_version, text_hash)
        if vector is not None:
            return vector
        vector = self.embedding_provider(embedding_text)
        self.cache.set(
            cache_key=cache_key,
            skill_text=embedding_text,
            vector=vector,
            model=self.embedding_model,
            version=self.config.embedding_version,
            text_hash=text_hash,
            source="runtime",
        )
        return vector

    def _validate_candidates(
        self,
        input_skill: str,
        normalized_skill: str,
        candidates: Sequence[SkillSearchCandidate],
        *,
        domain: str = "",
        category: str = "",
    ) -> SkillResolution:
        if not candidates:
            return SkillResolution(input_skill, normalized_skill, None, "unknown", "unknown", fallback_reason="no_candidates")

        top = candidates[0]

        frappe = _get_frappe()
        if frappe is not None and _doctype_exists(frappe, "Skill Master"):
            if not frappe.db.exists("Skill Master", top.skill_id):
                return SkillResolution(
                    input_skill,
                    normalized_skill,
                    None,
                    "unknown",
                    "unknown",
                    top.score,
                    False,
                    fallback_reason="deleted_canonical_skill",
                    candidates=list(candidates),
                )

        second = candidates[1] if len(candidates) > 1 else None
        gap = top.score - second.score if second else 1.0
        compatible, reason = self._business_rules_pass(top, domain=domain, category=category)

        if top.score >= self.config.auto_match_threshold and gap >= self.config.confidence_gap_threshold and compatible:
            logger.info(
                "SkillEmbeddingResolver: stage=qdrant_high_confidence input=%r canonical=%r score=%.4f gap=%.4f band=high",
                input_skill,
                top.skill_name,
                top.score,
                gap,
            )
            return SkillResolution(
                input_skill,
                normalized_skill,
                top.skill_name,
                "qdrant_high_confidence",
                "high",
                top.score,
                True,
                candidates=list(candidates),
            )

        if top.score >= self.config.uncertain_threshold and compatible:
            fallback_reason = "ambiguous_confidence_gap" if gap < self.config.confidence_gap_threshold else "below_auto_threshold"
            logger.info(
                "SkillEmbeddingResolver: stage=qdrant_uncertain input=%r top=%r score=%.4f gap=%.4f reason=%s",
                input_skill,
                top.skill_name,
                top.score,
                gap,
                fallback_reason,
            )
            return SkillResolution(
                input_skill,
                normalized_skill,
                None,
                "qdrant_uncertain",
                "uncertain",
                top.score,
                False,
                fallback_reason=fallback_reason,
                candidates=list(candidates),
            )

        fallback_reason = reason or "below_uncertain_threshold"
        logger.info(
            "SkillEmbeddingResolver: stage=unknown input=%r top=%r score=%.4f reason=%s",
            input_skill,
            top.skill_name,
            top.score,
            fallback_reason,
        )
        return SkillResolution(
            input_skill,
            normalized_skill,
            None,
            "unknown",
            "unknown",
            top.score,
            False,
            fallback_reason=fallback_reason,
            candidates=list(candidates),
        )

    def _business_rules_pass(self, candidate: SkillSearchCandidate, *, domain: str = "", category: str = "") -> tuple[bool, str]:
        if not candidate.active:
            return False, "inactive_candidate"
        if domain and candidate.domain and domain.strip().lower() != candidate.domain.strip().lower():
            return False, "domain_mismatch"
        if category and candidate.category and category.strip().lower() != candidate.category.strip().lower():
            return False, "category_mismatch"
        return True, ""


def build_skill_embedding_text(record: SkillMasterRecord) -> str:
    """Build rich canonical embedding text from Skill Master fields."""
    parts = [f"Skill Name: {record.skill_name}"]
    if record.aliases:
        parts.append("Aliases: " + ", ".join(record.aliases))
    if record.category:
        parts.append(f"Category: {record.category}")
    if record.domain:
        parts.append(f"Domain: {record.domain}")
    if record.description:
        parts.append(f"Description: {record.description}")
    return "\n".join(parts)


def build_runtime_skill_embedding_text(skill_name: str) -> str:
    normalized = normalize_skill(skill_name)
    return f"Skill Name: {normalized}\nNormalized Key: {get_skill_key(normalized)}"


def _default_embedding_provider() -> EmbeddingProvider:
    from job_search_ai.services.ai.embedding_service import EmbeddingService

    return EmbeddingService().embed


def _default_embedding_model() -> str:
    try:
        from job_search_ai.services.settings_service import SettingsService

        return str(SettingsService.get().embedding_model)
    except Exception:
        return "nomic-embed-text"


def _cache_key(normalized_key: str) -> str:
    return normalized_key.strip().lower()


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _utc_now() -> str:
    frappe = _get_frappe()
    if frappe is not None and hasattr(frappe, "utils") and hasattr(frappe.utils, "now"):
        return frappe.utils.now()
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _get_config_value(settings: Any | None, attr: str, env_var: str, default: Any) -> Any:
    if settings is not None:
        if hasattr(settings, "_get_value"):
            return settings._get_value(attr, env_var, default)
        value = getattr(settings, attr, None)
        if value not in (None, ""):
            return value
    return os.environ.get(env_var, default)


def _as_int(value: Any, default: int) -> int:
    try:
        value = int(value)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _as_float(value: Any, default: float) -> float:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return default
    return value if 0.0 <= value <= 1.0 else default


def _get_frappe() -> Any | None:
    try:
        import frappe

        if getattr(frappe, "db", None):
            return frappe
    except Exception:
        return None
    return None


def _doctype_exists(frappe: Any, doctype: str) -> bool:
    try:
        return bool(frappe.db.exists("DocType", doctype))
    except Exception:
        return False
