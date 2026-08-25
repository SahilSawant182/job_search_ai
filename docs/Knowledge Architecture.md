# Knowledge Architecture

> **Status**: MVP-Complete (Frozen for bug fixes only)
> **Last Updated**: 2026-07-23
> **Scope**: Skill Knowledge System — the foundation beneath the Skill Gap Agent, and the future Roadmap Agent.

---

## Overview

The Skill Knowledge System is a layered pipeline that transforms a student's raw self-reported skills into a semantically normalized, graph-expanded, deterministic set of canonical skill tokens that can be reliably compared against structured job requirements.

```
Student Raw Input
       │
       ▼
  Normalization          ← Clean text, split compound skills, remove filler words
       │
       ▼
  Alias Resolution       ← Collapse known synonyms (NLP → Natural Language Processing)
       │
       ▼
  Semantic Resolution    ← Qdrant vector search: map to a canonical Skill Master record
       │
       ▼
Relationship Expansion   ← Graph traversal: infer broader/narrower implied skills
       │
       ▼
 Skill Gap Analyzer      ← Deterministic diff against required skills
       │
       ▼
  Readiness Score        ← Weighted coverage metric
       │
       ▼
  Roadmap Agent          ← (Next) Priority-ordered learning path
```

---

## Components

### 1. Skill Master

**DocType**: `Skill Master`
**Purpose**: The single source of truth for all canonical skill names. Every skill in the system must exist here.

| Field | Type | Description |
|---|---|---|
| `skill_name` | Data | Canonical display name. e.g. `"Natural Language Processing"` |
| `active` | Check | Inactive skills are excluded from all matching |

**Rules**:
- Only active Skill Master records participate in gap analysis.
- Skill names are stored in their full, unabbreviated form.
- All other components reference skills by their Skill Master name.

---

### 2. Skill Alias

**DocType**: `Skill Alias`
**Purpose**: Maps common abbreviations and alternative spellings to their canonical Skill Master record. Resolved at normalization time — before any vector search.

| Field | Type | Description |
|---|---|---|
| `alias` | Data | The shorthand or alternate form. e.g. `"NLP"` |
| `skill_master` | Link → Skill Master | The canonical target. e.g. `"Natural Language Processing"` |

**Rules**:
- Aliases are resolved in `normalizer.py` before any other processing.
- One alias maps to exactly one canonical skill.
- Bidirectional aliases should be stored as separate records.

---

### 3. Skill Relationship

**DocType**: `Skill Relationship`
**Purpose**: Stores directed edges in the skill knowledge graph. Enables semantic expansion — knowing `AWS` implies knowing `EC2` and `Lambda`.

| Field | Type | Description |
|---|---|---|
| `from_skill` | Link → Skill Master | The source skill |
| `relation_type` | Select | One of: `Alias`, `Contains`, `Related`, `Prerequisite` |
| `to_skill` | Link → Skill Master | The target skill |
| `confidence` | Float | Reliability score, 0.0–1.0. Default `1.0` |
| `source_type` | Select | `Manual`, `Imported`, `LLM`, `System` |
| `source_name` | Data | Optional. e.g. `"ESCO"`, `"GPT-4"`, `"O*NET"` |
| `is_trusted_source` | Check | If `True`, loaded regardless of confidence. If `False`, must meet threshold. |
| `status` | Select | `Pending`, `Approved`, `Rejected`. Only `Approved` records are cached. |
| `active` | Check | Master on/off switch |

#### Relation Type Semantics

| Type | Implication | Direction | Example |
|---|---|---|---|
| `Alias` | A ↔ B (interchangeable) | Bidirectional | `ReactJS` ↔ `React` |
| `Contains` | A → B (A implies B) | A to B | `AWS` → `EC2` |
| `Related` | No implication | None | `Docker` ~ `Kubernetes` |
| `Prerequisite` | No implication (roadmap use only) | None | `Python` ← `Machine Learning` |

> **Design note**: `Parent` was deliberately removed. Inverse containment is derived from `Contains`, not stored redundantly.

#### Trust Policy

```
is_trusted_source = True
    → Always loaded into cache (confidence ignored)
    → Use for: Manual admin entries, curated imports (ESCO, O*NET)

is_trusted_source = False
    → Only loaded if confidence >= configured threshold
    → Use for: Raw LLM suggestions, unreviewed CSV imports
```

> **Future**: When importing large external taxonomies (ESCO, O*NET, Lightcast), consider a `Knowledge Source` DocType to normalize `source_name + is_trusted_source` into one record instead of repeating it across 200k+ relationships.

#### Status Lifecycle

```
LLM suggests relationship
         │
         ▼
    status = Pending       ← Not cached, not active
         │
    Admin reviews
         │
    ┌────┴────┐
    ▼         ▼
Approved   Rejected
(cached)  (ignored)
```

---

### 4. Qdrant Embeddings

**Service**: `SkillEmbeddingIndex` (`skill_embedding_index.py`)
**Purpose**: Stores dense vector representations of all Skill Master records. Enables fuzzy/semantic lookup when exact string matching fails.

**Key behaviours**:
- Vectors are generated via a sentence-transformer model.
- Embeddings are cached persistently to avoid re-computation.
- Stale vectors (for deleted/inactive skills) are purged automatically.
- Query: given a raw skill string, return the top-K nearest canonical skills with cosine similarity scores.

---

### 5. Semantic Resolver

**Service**: `SkillEmbeddingResolver` (`skill_embedding_index.py`)
**Purpose**: Given a raw or normalized skill string, resolve it to a canonical Skill Master record using Qdrant vector search.

**Resolution stages** (in priority order):
1. Exact key match
2. Semantic fingerprint match (token overlap heuristic)
3. Qdrant vector similarity (above threshold)
4. LLM disambiguation (optional fallback)

**Output**: A `SkillResolution` object with `canonical_skill`, `stage`, and `score`.

---

### 6. Relationship Resolver

**Service**: `relationship.py`
**Purpose**: In-memory graph cache and DFS traversal engine. Given a canonical skill, returns the full set of implied skills via `Alias` and `Contains` relationships.

**Key behaviours**:
- Cache is loaded once on first use from the database (active + approved + trust/confidence filtered).
- Cache is invalidated automatically on `Skill Relationship` `on_update` and `on_trash` hooks.
- Traversal uses DFS with a recursion stack to detect and log cycles without crashing:
  ```
  WARNING: SkillRelationship: cycle detected in graph path: A -> B -> C -> A
  ```
- `Related` and `Prerequisite` edges are stored but **not** traversed during skill matching (reserved for the Roadmap Agent).

**Constants** (use these — never hardcode the strings):
```python
RELATION_ALIAS = "Alias"
RELATION_CONTAINS = "Contains"
RELATION_RELATED = "Related"
RELATION_PREREQUISITE = "Prerequisite"
```

---

### 7. Semantic Skill Matcher

**Service**: `SemanticSkillMatcher` (`matcher.py`)
**Purpose**: Orchestrates the full pipeline. For a given student skills list and required skills list, produces a list of `SkillMatch` objects.

**Pipeline inside `canonicalize_inputs()`**:
```
student_skills
      │
_canonicalize_student_skills()   ← normalize + semantic resolve via Qdrant
      │
_expand_student_skills()         ← relationship graph expansion
      │
match against required_skills    ← fingerprint → qdrant → LLM stages
```

**Proficiency level rule**: When a skill is implied by multiple paths (e.g. student has `DSA` at `Advanced` and `Data Structures` at `Beginner`), the **highest level** is preserved.

---

### 8. Skill Gap Analyzer

**Service**: `SkillGapAnalyzer` (`analyzer.py`)
**Purpose**: Deterministic diff. Given matched and required skills, produces the structured gap report.

**Output fields**:
```json
{
  "matched_skills": [...],
  "missing_primary": [...],
  "missing_advanced": [...],
  "missing_expert": [...],
  "readiness_score": 42.5,
  "ready_for_job": false,
  "priority_order": [...]
}
```

**Rules**:
- No AI involved. Fully deterministic.
- Missing skills are grouped by proficiency tier (Primary / Advanced / Expert).
- `priority_order` lists missing skills in tier order for roadmap generation.

---

## Data Flow Diagram

```
┌──────────────────────────────────────────────────────────────┐
│                     Skill Knowledge System                   │
│                                                              │
│   Skill Master ──────────────────────────────┐              │
│        │                                     │              │
│        ├── Skill Alias                        │              │
│        │   (synonym resolution)              │              │
│        │                                     │              │
│        └── Skill Relationship ───────────────┤              │
│            (graph edges)                     │              │
│                 │                            │              │
│                 ▼                            ▼              │
│        Relationship Cache           Qdrant Embeddings        │
│        (in-memory graph)            (vector index)          │
│                 │                            │              │
│                 └────────────┬───────────────┘              │
│                              │                              │
│                              ▼                              │
│                   SemanticSkillMatcher                       │
│                   (pipeline orchestrator)                   │
│                              │                              │
│                              ▼                              │
│                   Skill Gap Analyzer                         │
│                   (deterministic diff)                       │
│                              │                              │
│                              ▼                              │
│                      Gap Report JSON                         │
│                              │                              │
│                              ▼                              │
│                   Roadmap Agent  ← (next)                   │
└──────────────────────────────────────────────────────────────┘
```

---

## What Is NOT In This System

To avoid confusion, the following are explicitly out of scope for the Skill Knowledge System:

| Topic | Decision |
|---|---|
| Graph databases (Neo4j) | Not needed. In-memory adjacency list is sufficient. |
| Weighted edge traversal | Not implemented. Trust + confidence is enough. |
| Recursive scoring / inference | No. The analyzer is deterministic. |
| Ontology frameworks (OWL, RDF) | Overcomplicated for this use case. |
| Runtime LLM matching | LLM is an optional fallback only, never primary. |

---

## Known Limitations & Future Work

| Item | Notes |
|---|---|
| `Knowledge Source` DocType | If importing ESCO/O\*NET at scale (200k+ relationships), normalize `source_name + is_trusted_source` into a separate entity instead of repeating per row. |
| `Relationship Suggestion` DocType | A staging area for LLM-suggested edges before admin approval. Not built yet — keep on roadmap. |
| Taxonomy versioning | `knowledge_version` was considered and removed. If you need reproducible snapshots, add versioning at the Skill Master / taxonomy level, not the edge level. |
| `Prerequisite` edges | Stored but currently unused by the matcher. Reserved for the Roadmap Agent to build learning sequences. |

---

## Test Suite Reference

| Test File | Covers |
|---|---|
| `test_relationship.py` | Graph expansion, alias/contains, cycle detection, status filtering, trust/confidence policy |
| `test_fixes.py` | Cache invalidation hooks, inactive skill filtering, concurrency, validation errors |
| `test_skill_normalizer.py` | Atomic decomposition, alias canonicalization, dangling word removal |
| `test_semantic_matcher.py` | Fingerprint matching, embedding similarity, resolution stages |
| `test_skill_embedding_index.py` | Vector index build, cache, upsert, purge |
| `test_skill_gap.py` | End-to-end integration: student → career → gap report |
