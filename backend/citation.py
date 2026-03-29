"""
Citation (REF token) management system.

Spec: docs/interfaces.md §2 (final_response event), docs/backend.md §2.4.

Each CitationManager is created per-interaction. It assigns [REF_N] tokens
to facts from the knowledge graph, mapping each to a source PDF and page.
The cloud model sees only opaque [REF_N] tokens — no filenames or pages leak.
During rehydration, [REF_N] → [N] for display, and the citation list is
attached to the final_response SSE event.
"""

from __future__ import annotations

import re


class CitationManager:
    """Per-interaction citation tracker.

    Usage:
        cm = CitationManager()
        ref = cm.add_ref("lab_report.pdf", 2, "Lab Report — Oct 2025, p.2")
        # ref == "[REF_1]"
        # Include ref in gatekeeper response text
        # Later: resolve [REF_1] → [1] for display
    """

    def __init__(self):
        self._counter: int = 0
        self._refs: list[dict] = []
        self._recent: list[str] = []  # tracks refs added since last get_refs_added()

    def add_ref(self, source_pdf: str, source_page: int, display_text: str) -> str:
        """Assign a new [REF_N] token for a fact.

        Each call creates a new REF — even if the same PDF+page is cited
        for a different fact.

        Returns:
            Token string, e.g. "[REF_1]"
        """
        self._counter += 1
        ref_id = f"REF_{self._counter}"
        token = f"[{ref_id}]"

        self._refs.append({
            "ref_id": ref_id,
            "index": self._counter,
            "display": display_text,
            "pdf": source_pdf,
            "page": source_page,
        })

        self._recent.append(ref_id)

        return token

    def get_all_refs(self) -> list[dict]:
        """Return all citation objects for the final_response SSE event.

        Format matches docs/interfaces.md §2 final_response.citations.
        """
        return list(self._refs)

    def resolve_refs_in_text(self, text: str) -> str:
        """Replace [REF_N] tokens with display indices [N].

        Handles both individual refs like [REF_1] and grouped refs like
        [REF_16, REF_26, REF_29] that Claude sometimes produces.
        """
        # First handle grouped refs: [REF_1, REF_2, REF_3] → [1], [2], [3]
        def group_replacer(match):
            inner = match.group(1)
            refs = re.findall(r"REF_(\d+)", inner)
            return ", ".join(f"[{n}]" for n in refs)

        text = re.sub(r"\[(REF_\d+(?:,\s*REF_\d+)+)\]", group_replacer, text)

        # Then handle individual refs: [REF_1] → [1]
        text = re.sub(r"\[REF_(\d+)\]", lambda m: f"[{m.group(1)}]", text)

        return text

    def get_refs_added(self) -> list[str]:
        """Return REF IDs added since the last call to this method.

        Used for the gatekeeper_response SSE event's refs_added field.
        Resets the tracker after each call.
        """
        added = list(self._recent)
        self._recent.clear()
        return added
