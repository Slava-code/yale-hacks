"""
MedGate Gatekeeper — local LLM-powered PHI detection and knowledge graph query layer.

Spec: docs/backend.md §2.

The gatekeeper uses a local LLM (via Ollama) for natural language understanding:
- Identifying PHI spans in user queries
- Parsing knowledge graph queries from the cloud model

All privacy-critical operations (token generation, string replacement, graph traversal,
citation assignment, rehydration) are deterministic code — NOT LLM output.
"""

from __future__ import annotations

import json
import httpx

from backend.token_manager import TokenMapping
from backend.citation import CitationManager
from backend import graph as graph_mod
from backend.graph import Graph, Node


GATEKEEPER_SYSTEM_PROMPT = """You are the MedGate Gatekeeper — a privacy-preserving clinical data librarian.

When given a raw clinician query, identify ALL Protected Health Information (PHI) in it.

Return a JSON array of PHI spans found. Each span has:
- "text": the exact PHI text as it appears in the query
- "type": one of PATIENT, PROVIDER, FAMILY, MRN, DATE, LOCATION, CONTACT

Example input: "Tell me about John Smith, he was seen by Dr. Chen at Springfield General on January 15"
Example output:
[
  {"text": "John Smith", "type": "PATIENT"},
  {"text": "Dr. Chen", "type": "PROVIDER"},
  {"text": "Springfield General", "type": "LOCATION"},
  {"text": "January 15", "type": "DATE"}
]

Rules:
- Identify patient names, provider names, family member names, MRNs, dates, locations, phone numbers, emails
- Do NOT flag clinical terms (conditions, symptoms, medications, lab values) as PHI
- Do NOT flag age (except 90+), sex, or generic descriptions as PHI
- Return ONLY the JSON array, no other text"""

KNOWLEDGE_QUERY_PROMPT = """You are parsing a clinical knowledge query. Determine what information is being requested.

Given the query, return a JSON object with:
- "action": one of "get_patient_labs", "get_patient_medications", "get_patient_conditions", "get_patient_visits", "get_patient_procedures", "get_patient_providers", "get_family_history", "search"
- "patient_id": the patient's graph ID if you can determine it, or null
- "search_query": if action is "search", what to search for

The query will contain tokens like [PATIENT_1] instead of real names.

Return ONLY the JSON object, no other text."""

# Maps field names to their PHI type for redaction
FIELD_PHI_TYPES = {
    "name": "PATIENT",
    "attending_provider": "PROVIDER",
    "prescribing_provider": "PROVIDER",
    "provider": "PROVIDER",
    "mrn": "MRN",
    "date": "DATE",
    "start_date": "DATE",
    "diagnosed_date": "DATE",
}


class Gatekeeper:
    def __init__(self, ollama_url: str = "http://localhost:11434", model: str = "qwen2.5:32b"):
        self.ollama_url = ollama_url
        self.model = model

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def deidentify_query(self, raw_query: str, kg: Graph) -> dict:
        """De-identify a raw clinician query.

        1. LLM identifies PHI spans
        2. Deterministic code generates tokens and performs replacement
        3. Resolves patient from graph to get their ID

        Returns:
            {
                "sanitized_query": str,
                "token_mapping": TokenMapping,
                "token_summary": dict,
                "patient_id": str | None,
            }
        """
        phi_spans = await self._identify_phi(raw_query)
        tm = TokenMapping()

        # Register all PHI spans
        for span in phi_spans:
            tm.add(span["text"], span["type"])

        sanitized = tm.apply(raw_query)

        # Try to resolve patient from the original query
        patient_id = None
        for span in phi_spans:
            if span["type"] == "PATIENT":
                patient = graph_mod.get_patient(kg, name=span["text"])
                if patient:
                    patient_id = patient.id
                    break

        return {
            "sanitized_query": sanitized,
            "token_mapping": tm,
            "token_summary": tm.get_summary(),
            "patient_id": patient_id,
        }

    async def query_knowledge_graph(
        self,
        question: str,
        token_mapping: TokenMapping,
        kg: Graph,
        citation_manager: CitationManager,
        patient_id: str | None = None,
    ) -> dict:
        """Handle a knowledge query from the cloud model.

        1. LLM parses what info is needed
        2. Code traverses the graph (using patient_id we already resolved)
        3. Code composes, redacts, and cites the response

        Returns:
            {
                "content": str (redacted with [REF_N] tokens),
                "accessed_nodes": list[str],
                "refs_added": list[str],
            }
        """
        parsed = await self._parse_knowledge_query(question)
        action = parsed.get("action", "search")

        # Use the patient_id passed in (from de-identification), fall back to LLM/token resolution
        if not patient_id:
            patient_id = parsed.get("patient_id")
        if not patient_id:
            patient_id = self._resolve_patient_from_tokens(token_mapping, kg)

        if not patient_id:
            return {
                "content": "Patient information not found in the knowledge graph.",
                "accessed_nodes": [],
                "refs_added": [],
            }

        # Dispatch to the right graph query
        raw_result = self._fetch_from_graph(action, patient_id, kg, parsed)
        accessed_ids = [patient_id]

        # Family history returns dicts, not Nodes — handle separately
        if raw_result and isinstance(raw_result[0], dict):
            parts = []
            for entry in raw_result:
                text = f"Family history: {entry.get('relation', 'relative')} — {entry.get('condition', 'unknown condition')}"
                if entry.get('diagnosed_age'):
                    text += f", diagnosed at age {entry['diagnosed_age']}"
                redacted = token_mapping.apply(text)
                if entry.get('source_pdf') and entry.get('source_page') is not None:
                    ref = citation_manager.add_ref(entry['source_pdf'], entry['source_page'], text[:50])
                    redacted += f" {ref}"
                parts.append(redacted)
            content = ". ".join(parts) + "." if parts else "No family history found."
            return {
                "content": content,
                "accessed_nodes": accessed_ids,
                "refs_added": citation_manager.get_refs_added(),
            }

        nodes = raw_result
        accessed_ids += [n.id for n in nodes]

        # Also include connected nodes for traversal path
        visits = graph_mod.get_patient_visits(kg, patient_id)
        for visit in visits:
            for node in nodes:
                # Check if this node is connected through this visit
                for edge in kg.edges:
                    if edge["source"] == visit.id and edge["target"] == node.id:
                        if visit.id not in accessed_ids:
                            accessed_ids.append(visit.id)

        if not nodes:
            return {
                "content": "The requested information is not available in the knowledge graph.",
                "accessed_nodes": accessed_ids,
                "refs_added": [],
            }

        result = self._compose_response(nodes, token_mapping, citation_manager)
        result["accessed_nodes"] = accessed_ids

        return result

    def rehydrate_response(
        self,
        cloud_response: str,
        token_mapping: TokenMapping,
        citation_manager: CitationManager,
    ) -> dict:
        """Re-hydrate a cloud model response.

        1. Replace PHI tokens with real values
        2. Replace [REF_N] with [N] display indices
        3. Attach citations list
        4. Destroy mappings

        Returns:
            {
                "content": str (with real names and [N] citations),
                "citations": list[dict],
            }
        """
        # Step 1: rehydrate PHI tokens
        content = token_mapping.rehydrate(cloud_response)

        # Step 2: resolve REF tokens to display indices
        content = citation_manager.resolve_refs_in_text(content)

        # Step 3: get citations
        citations = citation_manager.get_all_refs()

        # Step 4: destroy mappings
        token_mapping.destroy()

        return {
            "content": content,
            "citations": citations,
        }

    # ------------------------------------------------------------------
    # LLM interaction (these get mocked in tests)
    # ------------------------------------------------------------------

    async def _identify_phi(self, raw_query: str) -> list[dict]:
        """Call local LLM to identify PHI spans in a query."""
        try:
            response = await self._chat(GATEKEEPER_SYSTEM_PROMPT, raw_query)
            return json.loads(self._extract_json(response))
        except (json.JSONDecodeError, TypeError):
            # Fallback: return empty — no PHI detected
            return []
        except Exception:
            # Ollama connection/timeout/HTTP errors — fallback to no PHI detected
            return []

    async def _parse_knowledge_query(self, question: str) -> dict:
        """Call local LLM to parse what info a knowledge query is asking for."""
        try:
            response = await self._chat(KNOWLEDGE_QUERY_PROMPT, question)
            return json.loads(self._extract_json(response))
        except (json.JSONDecodeError, TypeError):
            return {"action": "search", "search_query": question}
        except Exception:
            # Ollama connection/timeout/HTTP errors — fallback to search
            return {"action": "search", "search_query": question}

    async def _chat(self, system_prompt: str, user_message: str) -> str:
        """Send a chat request to Ollama and return the response text."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.ollama_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message},
                    ],
                    "stream": False,
                    "options": {"temperature": 0.1},
                },
                timeout=120.0,
            )
        response.raise_for_status()
        return response.json()["message"]["content"]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_patient_from_tokens(self, tm: TokenMapping, kg: Graph) -> str | None:
        """Try to find a patient_id by looking up token values in the graph."""
        for token, value in tm.items():
            if "PATIENT" in token:
                patient = graph_mod.get_patient(kg, name=value)
                if patient:
                    return patient.id
        return None

    def _fetch_from_graph(
        self, action: str, patient_id: str, kg: Graph, parsed: dict
    ) -> list[Node]:
        """Dispatch to the right graph query function."""
        dispatch = {
            "get_patient_labs": lambda: graph_mod.get_patient_labs(kg, patient_id),
            "get_patient_medications": lambda: graph_mod.get_patient_medications(kg, patient_id),
            "get_patient_conditions": lambda: graph_mod.get_patient_conditions(kg, patient_id),
            "get_patient_visits": lambda: graph_mod.get_patient_visits(kg, patient_id),
            "get_patient_procedures": lambda: graph_mod.get_patient_procedures(kg, patient_id),
            "get_patient_providers": lambda: graph_mod.get_patient_providers(kg, patient_id),
            "get_family_history": lambda: graph_mod.get_family_history(kg, patient_id),
            "search": lambda: graph_mod.search_nodes(kg, parsed.get("search_query", "")),
        }
        fn = dispatch.get(action, dispatch["search"])
        return fn()

    def _compose_response(
        self,
        nodes: list[Node],
        token_mapping: TokenMapping,
        citation_manager: CitationManager,
    ) -> dict:
        """Compose a redacted response with citations from graph nodes.

        Returns:
            {"content": str, "refs_added": list[str]}
        """
        parts = []

        for node in nodes:
            # Build a text description of this node
            text = self._node_to_text(node)

            # Redact PHI in the text
            # First, register any PHI fields we haven't seen yet
            for field_name, field_data in node.fields.items():
                if field_data.get("phi", False) and field_name in FIELD_PHI_TYPES:
                    value = str(field_data["value"])
                    token_mapping.add(value, FIELD_PHI_TYPES[field_name])

            redacted_text = token_mapping.apply(text)

            # Add citation
            if node.source_pdf and node.source_page is not None:
                display = f"{node.label}"
                ref = citation_manager.add_ref(node.source_pdf, node.source_page, display)
                redacted_text += f" {ref}"

            parts.append(redacted_text)

        content = ". ".join(parts) + "." if parts else "No information found."
        refs_added = citation_manager.get_refs_added()

        return {"content": content, "refs_added": refs_added}

    def _node_to_text(self, node: Node) -> str:
        """Convert a graph node to a natural text description."""
        node_type = node.type

        if node_type == "lab_result":
            name = node.field_value("test_name") or node.label
            value = node.field_value("value") or ""
            unit = node.field_value("unit") or ""
            ref_range = node.field_value("reference_range") or ""
            flag = node.field_value("flag") or ""
            parts = [f"{name}: {value}"]
            if unit:
                parts[0] += f" {unit}"
            if ref_range:
                parts.append(f"reference {ref_range}")
            if flag and flag != "normal":
                parts.append(f"({flag})")
            return ", ".join(parts)

        elif node_type == "medication":
            name = node.field_value("name") or node.label
            dosage = node.field_value("dosage") or ""
            freq = node.field_value("frequency") or ""
            status = node.field_value("status") or ""
            parts = [name]
            if dosage:
                parts[0] += f" {dosage}"
            if freq:
                parts.append(freq)
            if status:
                parts.append(f"({status})")
            return ", ".join(parts)

        elif node_type == "condition":
            name = node.field_value("name") or node.label
            status = node.field_value("status") or ""
            icd = node.field_value("icd_code") or ""
            parts = [name]
            if status:
                parts.append(f"status: {status}")
            if icd:
                parts.append(f"ICD: {icd}")
            return ", ".join(parts)

        elif node_type == "visit":
            vtype = node.field_value("visit_type") or ""
            complaint = node.field_value("chief_complaint") or ""
            provider = node.field_value("attending_provider") or ""
            date = node.field_value("date") or ""
            parts = []
            if vtype:
                parts.append(f"{vtype} visit")
            if date:
                parts.append(f"on {date}")
            if provider:
                parts.append(f"with {provider}")
            if complaint:
                parts.append(f"for {complaint}")
            return ", ".join(parts) if parts else node.label

        elif node_type == "procedure":
            name = node.field_value("name") or node.label
            outcome = node.field_value("outcome") or ""
            parts = [name]
            if outcome:
                parts.append(f"outcome: {outcome}")
            return ", ".join(parts)

        elif node_type == "provider":
            name = node.field_value("name") or node.label
            dept = node.field_value("department") or ""
            role = node.field_value("role") or ""
            parts = [name]
            if role:
                parts.append(role)
            if dept:
                parts.append(dept)
            return ", ".join(parts)

        else:
            return node.label

    @staticmethod
    def _extract_json(text: str) -> str:
        """Extract JSON from LLM response that might have markdown fences or extra text."""
        text = text.strip()
        # Try to find JSON array or object
        if text.startswith("```"):
            lines = text.split("\n")
            json_lines = []
            in_block = False
            for line in lines:
                if line.startswith("```") and not in_block:
                    in_block = True
                    continue
                elif line.startswith("```") and in_block:
                    break
                elif in_block:
                    json_lines.append(line)
            text = "\n".join(json_lines)

        # Find first [ or {
        for i, c in enumerate(text):
            if c in ("[", "{"):
                # Find matching close
                depth = 0
                close = "]" if c == "[" else "}"
                for j in range(i, len(text)):
                    if text[j] == c:
                        depth += 1
                    elif text[j] == close:
                        depth -= 1
                        if depth == 0:
                            return text[i : j + 1]
        return text
