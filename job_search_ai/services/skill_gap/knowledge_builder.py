# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import logging
import re
import urllib.request
import urllib.error
import frappe
from datetime import datetime

from job_search_ai.services.skill_gap.normalizer import normalize_skill, get_skill_key

logger = logging.getLogger(__name__)

# Hard timeout for LLM calls (seconds)
_TIMEOUT = 30


@frappe.whitelist()
def learn_skill_async(raw_skill: str, source: str = "SkillGapService"):
    """
    Enqueued background task to learn an unknown skill.
    """
    try:
        builder = SkillKnowledgeBuilder()
        builder.learn_skill(raw_skill, source)
    except Exception as e:
        logger.error("Error in learn_skill_async background job for %r: %s", raw_skill, e)


class SkillKnowledgeBuilder:
    """
    Self-learning Skill Knowledge Builder.
    
    Responsible for identifying unknown skills, invoking LLM to determine their nature,
    and automatically populating the Skill Master, Skill Alias, and Skill Relationship
    DocTypes if confidence is high, or queuing them in Unknown Skill if confidence is low.
    """

    def __init__(self, settings=None):
        if settings is None:
            from job_search_ai.services.settings_service import SettingsService
            settings = SettingsService.get()
        self.settings = settings

    def learn_skill(self, raw_skill: str, source: str = "SkillGapService") -> bool:
        """
        Attempt to learn an unknown skill.
        
        Returns:
            bool: True if the skill was successfully learned and resolved, False otherwise.
        """
        if not raw_skill or not raw_skill.strip():
            return False

        normalized_skill = normalize_skill(raw_skill)
        normalized_key = get_skill_key(normalized_skill)
        if not normalized_key:
            return False

        # 1. Double check if it already exists or was resolved to avoid redundant LLM calls
        if frappe.db.exists("Skill Master", normalized_skill):
            return True
        if frappe.db.exists("Skill Master", {"name": ("like", f"%{normalized_key}%")}):
            return True
        if frappe.db.exists("Skill Alias", {"alias": raw_skill}) or frappe.db.exists("Skill Alias", {"alias": normalized_skill}):
            return True

        # Check if already processed (or currently in progress) in Unknown Skill
        if frappe.db.exists("Unknown Skill", normalized_key):
            try:
                # Use for_update=True to perform transaction-safe read/lock on the record
                unknown_doc = frappe.get_doc("Unknown Skill", normalized_key, for_update=True)
                if unknown_doc.status in ["Learned", "Merged"]:
                    return True
                
                # Check for stale locks / failed runs (older than 15 minutes)
                modified = unknown_doc.modified
                if isinstance(modified, str):
                    try:
                        modified = datetime.strptime(modified, "%Y-%m-%d %H:%M:%S.%f")
                    except ValueError:
                        try:
                            modified = datetime.strptime(modified, "%Y-%m-%d %H:%M:%S")
                        except ValueError:
                            modified = None
                
                if modified:
                    if modified.tzinfo is not None:
                        modified = modified.replace(tzinfo=None)
                    delta = (datetime.now() - modified).total_seconds()
                    if unknown_doc.status == "Error" or (unknown_doc.status == "Pending" and delta > 900):
                        logger.info("SkillKnowledgeBuilder: Found stale lock/error for %r (modified %d sec ago). Retrying.", raw_skill, delta)
                        unknown_doc.status = "Pending"
                        unknown_doc.confidence = 0.0
                        unknown_doc.source = source
                        unknown_doc.llm_response = "Retrying stale lock/error: LLM call pending"
                        unknown_doc.save(ignore_permissions=True)
                        frappe.db.commit()
                    else:
                        # Currently processing by another worker, exit early
                        return False
                else:
                    return False
            except Exception as e:
                logger.warning("Failed during stale lock check for %r: %s", raw_skill, e)
                return False
        else:
            # 2. Try to insert lock placeholder to block parallel/duplicate concurrent requests
            try:
                frappe.get_doc({
                    "doctype": "Unknown Skill",
                    "normalized_key": normalized_key,
                    "raw_text": raw_skill,
                    "normalized_text": normalized_skill,
                    "status": "Pending",
                    "confidence": 0.0,
                    "source": source,
                    "llm_response": "LLM call pending or in progress"
                }).insert(ignore_permissions=True)
                frappe.db.commit()
            except frappe.DuplicateEntryError:
                try:
                    status = frappe.db.get_value("Unknown Skill", normalized_key, "status")
                    if status in ["Learned", "Merged"]:
                        return True
                except Exception:
                    pass
                return False

        # 3. Retrieve some active canonical skills to help the LLM contextualize
        active_skills = []
        try:
            active_skills_rows = frappe.get_all("Skill Master", filters={"active": 1}, fields=["skill_name"], limit=200)
            active_skills = [row["skill_name"] for row in active_skills_rows]
        except Exception as e:
            logger.warning("SkillKnowledgeBuilder: failed to fetch active skills for prompt context: %s", e)

        # 4. Call the LLM
        prompt = self._build_prompt(raw_skill, normalized_skill, active_skills)
        raw_response = ""
        try:
            raw_response = self._execute_llm(prompt)
            parsed_raw = self._parse_response(raw_response)
            parsed = self._validate_llm_payload(parsed_raw, normalized_skill)
        except Exception as exc:
            logger.warning("SkillKnowledgeBuilder: LLM extraction or validation failed for %r: %s", raw_skill, exc)
            parsed = {"confidence": 0.0, "error": str(exc)}

        # 5. Determine auto-learning based on confidence threshold
        threshold = 0.85
        try:
            val = frappe.db.get_single_value("Job Search AI Settings", "skill_learning_confidence_threshold")
            if val is not None and float(val) > 0.0:
                threshold = float(val)
        except Exception:
            pass

        confidence = parsed.get("confidence", 0.0)
        has_error = bool(parsed.get("error"))

        if not has_error and confidence >= threshold:
            # Auto-learn the skill
            try:
                canonical = parsed.get("canonical_skill") or normalized_skill
                is_new = parsed.get("new_skill", True)

                # Find or create Skill Master (Resolving conflicts using cached normalize_skill)
                master_doc = None
                existing_canonical = normalize_skill(canonical)
                if existing_canonical and frappe.db.exists("Skill Master", existing_canonical):
                    master_doc = frappe.get_doc("Skill Master", existing_canonical)

                if not master_doc:
                    master_doc = frappe.new_doc("Skill Master")
                    master_doc.skill_name = canonical
                    master_doc.category = "Auto-learned"
                    master_doc.domain = "Software Engineering"
                    master_doc.active = 1
                    master_doc.insert(ignore_permissions=True)

                # Add aliases globally validating no duplication exists across Skill Master/Skill Alias
                for alias in parsed.get("aliases", []):
                    if not alias or alias.lower().strip() == canonical.lower().strip():
                        continue
                    
                    # Skip if alias is already registered as a main canonical skill
                    if frappe.db.exists("Skill Master", alias):
                        continue
                    
                    # Skip if alias is already registered on another skill
                    if frappe.db.exists("Skill Alias", {"alias": alias}):
                        continue

                    alias_exists = False
                    for row in getattr(master_doc, "aliases", []):
                        if row.alias.lower().strip() == alias.lower().strip():
                            alias_exists = True
                            break
                    if not alias_exists:
                        master_doc.append("aliases", {
                            "alias": alias,
                            "canonical_skill": master_doc.skill_name
                        })
                master_doc.save(ignore_permissions=True)

                # Create relationships
                for rel in parsed.get("relationships", []):
                    to_skill = rel.get("to_skill")
                    relation_type = rel.get("relation_type")
                    rel_confidence = rel.get("confidence", 1.0)
                    if not to_skill or not relation_type:
                        continue

                    # Prevent self-referential relationships
                    if get_skill_key(master_doc.skill_name) == get_skill_key(to_skill):
                        continue

                    # Ensure target skill exists in Skill Master.
                    # If it does not exist, do NOT automatically create it.
                    # Instead, stage it in Unknown Skill as Pending so it is learned or validated separately,
                    # and skip this relationship.
                    if not frappe.db.exists("Skill Master", to_skill):
                        to_normalized = normalize_skill(to_skill)
                        to_key = get_skill_key(to_normalized)
                        if to_key and not frappe.db.exists("Unknown Skill", to_key):
                            try:
                                frappe.get_doc({
                                    "doctype": "Unknown Skill",
                                    "normalized_key": to_key,
                                    "raw_text": to_skill,
                                    "normalized_text": to_normalized,
                                    "status": "Pending",
                                    "confidence": 0.0,
                                    "source": "SkillKnowledgeBuilder_Related",
                                    "llm_response": "Staged from related skill relationship of " + master_doc.skill_name
                                }).insert(ignore_permissions=True)
                            except Exception as e:
                                logger.warning("Failed to stage target skill %r in Unknown Skill: %s", to_skill, e)
                        continue

                    # Validate relation type
                    if relation_type not in ["Alias", "Contains", "Related", "Prerequisite"]:
                        relation_type = "Related"

                    if not frappe.db.exists("Skill Relationship", {"from_skill": master_doc.skill_name, "to_skill": to_skill, "relation_type": relation_type}):
                        try:
                            rel_doc = frappe.new_doc("Skill Relationship")
                            rel_doc.from_skill = master_doc.skill_name
                            rel_doc.relation_type = relation_type
                            rel_doc.to_skill = to_skill
                            rel_doc.confidence = rel_confidence
                            rel_doc.source_type = "LLM"
                            rel_doc.source_name = "SkillKnowledgeBuilder"
                            rel_doc.is_trusted_source = 0
                            rel_doc.status = "Approved"
                            rel_doc.active = 1
                            rel_doc.insert(ignore_permissions=True)
                        except Exception as e:
                            logger.warning("Failed to create skill relationship %r -> %r: %s", master_doc.skill_name, to_skill, e)

                # Sync Qdrant embedding
                try:
                    from job_search_ai.services.skill_gap.skill_embedding_index import SkillEmbeddingBuilder
                    emb_builder = SkillEmbeddingBuilder()
                    emb_builder.sync_skill(master_doc.skill_name)
                except Exception as e:
                    logger.warning("Failed to sync embedding for auto-learned skill %r: %s", master_doc.skill_name, e)

                # Invalidate resolver caches
                from job_search_ai.services.skill_gap.normalizer import invalidate_normalization_cache
                from job_search_ai.services.skill_gap.relationship import invalidate_relationship_cache
                invalidate_normalization_cache()
                invalidate_relationship_cache()

                # Mark Unknown Skill record as Learned
                unknown_doc = frappe.get_doc("Unknown Skill", normalized_key)
                unknown_doc.status = "Learned"
                unknown_doc.confidence = confidence
                unknown_doc.llm_response = json.dumps(parsed)
                unknown_doc.save(ignore_permissions=True)
                frappe.db.commit()
                return True

            except Exception as e:
                logger.error("SkillKnowledgeBuilder: failed during database auto-learning of %r: %s", raw_skill, e)
                # Fallback to Error status
                try:
                    unknown_doc = frappe.get_doc("Unknown Skill", normalized_key)
                    unknown_doc.status = "Error"
                    unknown_doc.llm_response = json.dumps({"error": str(e), "parsed": parsed})
                    unknown_doc.save(ignore_permissions=True)
                    frappe.db.commit()
                except Exception:
                    pass
                return False
        else:
            # Low confidence, parsing error, or execution failure: save details in Unknown Skill
            try:
                unknown_doc = frappe.get_doc("Unknown Skill", normalized_key)
                if has_error:
                    unknown_doc.status = "Error"
                else:
                    unknown_doc.status = "Pending"
                unknown_doc.confidence = confidence
                unknown_doc.llm_response = json.dumps(parsed) if isinstance(parsed, dict) else str(raw_response)
                unknown_doc.save(ignore_permissions=True)
                frappe.db.commit()
            except Exception as e:
                logger.warning("Failed to update Unknown Skill with status info: %s", e)
            return False

    def _validate_llm_payload(self, parsed: dict, normalized_skill: str) -> dict:
        if not isinstance(parsed, dict):
            raise ValueError("LLM response is not a valid JSON object")

        # 1. Canonical skill validation
        canonical = parsed.get("canonical_skill")
        if not canonical or not isinstance(canonical, str) or not canonical.strip():
            raise ValueError("Canonical skill name cannot be empty")
        canonical = canonical.strip()
        parsed["canonical_skill"] = canonical

        # 2. Boolean validation
        parsed["new_skill"] = bool(parsed.get("new_skill", True))

        # 3. Aliases validation
        aliases = parsed.get("aliases")
        if aliases is None:
            aliases = []
        if not isinstance(aliases, list):
            raise ValueError("Aliases must be a list")

        valid_aliases = []
        seen_aliases = set()
        for alias in aliases:
            if not isinstance(alias, str):
                raise ValueError("Aliases must be strings")
            if not alias.strip():
                raise ValueError("Alias list contains empty or invalid strings")
            cleaned = alias.strip()
            if cleaned.lower() == canonical.lower():
                raise ValueError("Alias cannot be identical to canonical skill name")
            if cleaned.lower() in seen_aliases:
                raise ValueError("Duplicate aliases found in response")
            seen_aliases.add(cleaned.lower())
            valid_aliases.append(cleaned)
        parsed["aliases"] = valid_aliases

        # 4. Relationships validation
        relationships = parsed.get("relationships")
        if relationships is None:
            relationships = []
        if not isinstance(relationships, list):
            raise ValueError("Relationships must be a list")

        valid_rels = []
        seen_rels = set()
        for rel in relationships:
            if not isinstance(rel, dict):
                raise ValueError("Relationship entry must be a dictionary")
            to_skill = rel.get("to_skill")
            relation_type = rel.get("relation_type")
            confidence = rel.get("confidence", 1.0)

            if not to_skill or not isinstance(to_skill, str) or not to_skill.strip():
                raise ValueError("Relationship to_skill or relation_type cannot be empty")
            if not relation_type or not isinstance(relation_type, str) or not relation_type.strip():
                raise ValueError("Relationship to_skill or relation_type cannot be empty")

            to_skill = to_skill.strip()
            relation_type = relation_type.strip()

            if relation_type not in ["Alias", "Contains", "Related", "Prerequisite"]:
                raise ValueError(f"Invalid relationship type: {relation_type}")

            # Check for self-reference
            if get_skill_key(canonical) == get_skill_key(to_skill):
                raise ValueError("Self-referential relationships are not allowed")

            # Check for duplicates
            rel_key = (get_skill_key(to_skill), relation_type.lower())
            if rel_key in seen_rels:
                raise ValueError("Duplicate relationships found in response")
            seen_rels.add(rel_key)

            try:
                confidence = float(confidence)
                if not (0.0 <= confidence <= 1.0):
                    confidence = 1.0
            except (ValueError, TypeError):
                confidence = 1.0

            valid_rels.append({
                "to_skill": to_skill,
                "relation_type": relation_type,
                "confidence": confidence
            })

        parsed["relationships"] = valid_rels

        # 5. Cycle Detection
        self._check_graph_cycles(canonical, valid_rels)

        return parsed

    def _check_graph_cycles(self, canonical_skill: str, proposed_relationships: list) -> None:
        db_rels = []
        try:
            db_rels = frappe.get_all(
                "Skill Relationship",
                filters={"active": 1, "relation_type": ["in", ["Contains", "Prerequisite"]]},
                fields=["from_skill", "to_skill", "relation_type"]
            )
        except Exception as e:
            logger.warning("SkillKnowledgeBuilder: failed to fetch relationships for cycle check: %s", e)

        graph = {}
        def add_edge(u, v, rel_type):
            u_key = get_skill_key(u)
            v_key = get_skill_key(v)
            if not u_key or not v_key:
                return
            if u_key not in graph:
                graph[u_key] = []
            graph[u_key].append((v_key, rel_type))

        for r in db_rels:
            add_edge(r.from_skill, r.to_skill, r.relation_type)

        # Add proposed relationships
        has_proposed_edges = False
        for r in proposed_relationships:
            if r["relation_type"] in ["Contains", "Prerequisite"]:
                add_edge(canonical_skill, r["to_skill"], r["relation_type"])
                has_proposed_edges = True

        if not has_proposed_edges:
            return

        # DFS starting from canonical_skill
        canonical_key = get_skill_key(canonical_skill)
        visited = set()
        rec_stack = set()

        def dfs(node):
            visited.add(node)
            rec_stack.add(node)

            for neighbor, rel_type in graph.get(node, []):
                if neighbor not in visited:
                    if dfs(neighbor):
                        return True
                elif neighbor in rec_stack:
                    if neighbor == canonical_key:
                        return True

            rec_stack.remove(node)
            return False

        if dfs(canonical_key):
            raise ValueError("Circular reference detected in relationship graph")

    def _build_prompt(self, raw_skill: str, normalized_skill: str, active_skills: list[str]) -> str:
        existing_skills_str = ", ".join(active_skills[:150])
        return (
            "You are a skill taxonomy builder for a professional career platform. "
            f"Analyze the raw skill: {raw_skill!r} (normalized: {normalized_skill!r}).\n\n"
            "Identify:\n"
            "1. Is this a completely new skill or a variant/acronym/alias of an existing one?\n"
            "2. What is its canonical display name? Keep it clean and standard (e.g. 'Natural Language Processing' instead of 'nlp').\n"
            "3. Any aliases or acronyms for this skill (e.g. ['NLP', 'Natural Language Processing']).\n"
            "4. Relationships with other canonical skills. Use these relation types:\n"
            "   - 'Contains': Broader topic containing narrower topic (e.g., 'AWS' Contains 'EC2').\n"
            "   - 'Prerequisite': A skill that must be learned first (e.g., 'Python' is a prerequisite of 'Django').\n"
            "   - 'Related': Similar skills in the same domain.\n"
            "   - 'Alias': Alternative names.\n"
            "5. A confidence score between 0.0 and 1.0 reflecting how sure you are.\n\n"
            f"Existing skills in the database you can reference or link to: [{existing_skills_str}]\n\n"
            "Examples:\n"
            "Example 1:\n"
            "Input Raw Skill: 'nlp'\n"
            "Output JSON:\n"
            "{\n"
            '  "canonical_skill": "Natural Language Processing",\n'
            '  "new_skill": false,\n'
            '  "aliases": ["NLP", "N.L.P.", "Natural Language Processing Techniques"],\n'
            '  "relationships": [\n'
            '    {\n'
            '      "to_skill": "Machine Learning",\n'
            '      "relation_type": "Related",\n'
            '      "confidence": 0.95\n'
            '    }\n'
            '  ],\n'
            '  "confidence": 0.99\n'
            "}\n\n"
            "Example 2:\n"
            "Input Raw Skill: 'aws lambda'\n"
            "Output JSON:\n"
            "{\n"
            '  "canonical_skill": "AWS Lambda",\n'
            '  "new_skill": true,\n'
            '  "aliases": ["Lambda", "Amazon Lambda"],\n'
            '  "relationships": [\n'
            '    {\n'
            '      "to_skill": "Amazon Web Services",\n'
            '      "relation_type": "Prerequisite",\n'
            '      "confidence": 0.90\n'
            '    }\n'
            '  ],\n'
            '  "confidence": 0.95\n'
            "}\n\n"
            "Return ONLY a valid JSON object matching the schema below. No explanation or markdown.\n"
            "Schema:\n"
            "{\n"
            '  "canonical_skill": "Canonical Skill Name",\n'
            '  "new_skill": true,\n'
            '  "aliases": ["Alias 1", "Alias 2"],\n'
            '  "relationships": [\n'
            '    {\n'
            '      "to_skill": "Target Skill Name",\n'
            '      "relation_type": "Contains/Prerequisite/Related/Alias",\n'
            '      "confidence": 0.95\n'
            '    }\n'
            '  ],\n'
            '  "confidence": 0.98\n'
            "}"
        )

    def _execute_llm(self, prompt: str) -> str:
        provider = (self.settings.llm_provider or "ollama").lower().strip()
        
        if provider == "omniroute":
            import os
            api_key = os.getenv("OMNIROUTE_API_KEY")
            if not api_key:
                if frappe.local and getattr(frappe.local, "initialised", False):
                    api_key = frappe.conf.get("omniroute_api_key")
            base_url = self.settings.omniroute_base_url or "http://localhost:20128/v1"
            model = self.settings.omniroute_model or "career-agent"
            
            from openai import OpenAI
            client = OpenAI(base_url=base_url, api_key=api_key or "")
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                timeout=_TIMEOUT,
            )
            return resp.choices[0].message.content or ""
        else:
            endpoint = self.settings.ollama_endpoint
            model = self.settings.default_llm_model or "qwen2.5:1.5b"
            
            payload = {
                "model": model,
                "prompt": prompt,
                "stream": False,
                "format": "json",
            }
            req = urllib.request.Request(
                endpoint,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                body = resp.read().decode("utf-8")
                return json.loads(body).get("response", "").strip()

    def _parse_response(self, raw_text: str) -> dict:
        if not raw_text or not raw_text.strip():
            return {"confidence": 0.0}

        cleaned = raw_text.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            match = re.search(r'\{.*\}', cleaned, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except json.JSONDecodeError:
                    pass
        return {"confidence": 0.0}
