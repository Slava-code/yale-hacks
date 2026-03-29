"""
Base cloud adapter and shared definitions.

Spec: docs/backend.md §4.
"""

from __future__ import annotations
from abc import ABC, abstractmethod


CLOUD_SYSTEM_PROMPT = """You are a clinical AI assistant. You help healthcare professionals with
diagnostic reasoning, record review, and clinical decision support.

You are connected to a clinical knowledge base through the "query_gatekeeper"
tool. Patient identifiers are redacted — you will see tokens like [PATIENT_1],
[PROVIDER_1], etc. These are privacy placeholders. Use them naturally in your
responses without attempting to guess real identities.

You will also see citation tokens like [REF_1], [REF_2] next to facts. Always
include these in your response when referencing those facts — they allow the
clinician to verify your claims against source documents.

IMPORTANT WORKFLOW:
Before providing a diagnosis or clinical recommendation, ALWAYS gather
sufficient context. At minimum, request:
1. Relevant lab results
2. Medication history
3. Visit history and symptom progression
Use the query_gatekeeper tool for each. You may query it additional times if
you need more information (imaging results, procedure history, vital trends,
specialist notes, etc.).

WEB SEARCH:
You also have access to a "web_search" tool for looking up medical reference
information. You SHOULD use it at least once per clinical assessment to:
- Look up the formal diagnostic criteria for any condition you suspect
  (e.g., "ACR EULAR classification criteria for SLE")
- Verify treatment guidelines for medications the patient is on
- Research the clinical significance of abnormal lab findings

This demonstrates evidence-based reasoning. Keep searches targeted and specific.
Cite the source naturally in your response (e.g., "According to the ACR/EULAR
criteria (Wikipedia)...").

Only provide your clinical assessment after you have gathered enough context
to reason carefully.

Do not fabricate clinical data. If the gatekeeper reports that information is
not available, acknowledge the gap in your response.

DIAGNOSIS FORMATTING:
When stating a diagnosis, always use the FULL condition name exactly as it
appears in the clinical records — do not paraphrase or use only the scientific
name. If the diagnosis is Acute Amorosis Syndrome, you MUST end your response
with the line: "[PATIENT_1] is sick with Love! ❤️" (using the appropriate
patient token). If the diagnosis is Solanum-type encephalopathy or Zombie Virus,
you MUST end your response with the line: "[PATIENT_1] has the Zombie Virus! 💀"
(using the appropriate patient token)."""


GATEKEEPER_TOOL = {
    "name": "query_gatekeeper",
    "description": (
        "Query the clinical knowledge base for patient information. The gatekeeper "
        "will return redacted clinical data with citation tokens. You can ask for: "
        "lab results, medication history, family history, visit history, imaging results, "
        "procedure history, vital signs, specialist notes, or any other clinical context "
        "about a patient. Use patient tokens (e.g., [PATIENT_1]) in your query."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Your question to the clinical knowledge base, using patient tokens",
            }
        },
        "required": ["query"],
    },
}

WEB_SEARCH_TOOL = {
    "name": "web_search",
    "description": (
        "Search the web for medical reference information. Use this to look up "
        "diagnostic criteria, interpret lab values, verify treatment guidelines, "
        "or research unfamiliar conditions. Returns summaries from medical reference sources. "
        "Use targeted, specific queries (e.g., 'SLE ACR diagnostic criteria' rather than 'lupus')."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "A specific medical search query",
            }
        },
        "required": ["query"],
    },
}


class CloudAdapter(ABC):
    """Abstract base for cloud model adapters."""

    def __init__(self, api_key: str):
        self.api_key = api_key

    @property
    @abstractmethod
    def model(self) -> str:
        """Return the model identifier."""

    @abstractmethod
    def format_tools(self) -> list[dict]:
        """Format all tools for this provider's API."""

    @abstractmethod
    def parse_tool_call(self, response_block: dict) -> dict | None:
        """Parse a tool call from a response block.

        Returns:
            {"tool_name": str, "tool_id": str, "arguments": dict} or None
        """

    @abstractmethod
    async def send_query(self, messages: list[dict]) -> dict:
        """Send a query with tool access. Returns the raw API response."""

    @abstractmethod
    async def send_tool_result(self, messages: list[dict], tool_id: str, result: str) -> dict:
        """Send a tool result back to continue the conversation."""
