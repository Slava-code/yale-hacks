"""Tests for the citation (REF token) management system."""

import pytest
from backend.citation import CitationManager


class TestAddRef:
    def test_first_ref_is_ref_1(self):
        cm = CitationManager()
        ref = cm.add_ref("lab_report_smith_2025_oct.pdf", 2, "Lab Report — Oct 2025, p.2")
        assert ref == "[REF_1]"

    def test_increments(self):
        cm = CitationManager()
        r1 = cm.add_ref("report.pdf", 1, "Report p.1")
        r2 = cm.add_ref("report.pdf", 2, "Report p.2")
        r3 = cm.add_ref("other.pdf", 1, "Other p.1")
        assert r1 == "[REF_1]"
        assert r2 == "[REF_2]"
        assert r3 == "[REF_3]"

    def test_same_source_different_refs(self):
        """Even same PDF+page gets a new REF if added again (each fact is distinct)."""
        cm = CitationManager()
        r1 = cm.add_ref("report.pdf", 2, "ANA result")
        r2 = cm.add_ref("report.pdf", 2, "ESR result")
        assert r1 != r2


class TestGetAllRefs:
    def test_returns_citation_objects(self):
        cm = CitationManager()
        cm.add_ref("lab_report_smith_2025_oct.pdf", 2, "Lab Report — Oct 2025, p.2")
        cm.add_ref("progress_note_smith_2025_aug.pdf", 1, "Progress Note — Aug 2025, p.1")
        refs = cm.get_all_refs()
        assert len(refs) == 2
        assert refs[0] == {
            "ref_id": "REF_1",
            "index": 1,
            "display": "Lab Report — Oct 2025, p.2",
            "pdf": "lab_report_smith_2025_oct.pdf",
            "page": 2,
        }
        assert refs[1] == {
            "ref_id": "REF_2",
            "index": 2,
            "display": "Progress Note — Aug 2025, p.1",
            "pdf": "progress_note_smith_2025_aug.pdf",
            "page": 1,
        }

    def test_empty_when_no_refs(self):
        cm = CitationManager()
        assert cm.get_all_refs() == []


class TestResolveRefsInText:
    def test_replaces_ref_tokens_with_indices(self):
        cm = CitationManager()
        cm.add_ref("report.pdf", 2, "Lab Report")
        cm.add_ref("note.pdf", 1, "Progress Note")
        text = "ANA positive [REF_1]. Headaches persisting [REF_2]."
        result = cm.resolve_refs_in_text(text)
        assert result == "ANA positive [1]. Headaches persisting [2]."

    def test_handles_multiple_same_ref(self):
        cm = CitationManager()
        cm.add_ref("report.pdf", 2, "Lab Report")
        text = "ANA positive [REF_1] and ESR elevated [REF_1]."
        result = cm.resolve_refs_in_text(text)
        assert result == "ANA positive [1] and ESR elevated [1]."

    def test_no_refs_returns_unchanged(self):
        cm = CitationManager()
        text = "Patient has headaches."
        assert cm.resolve_refs_in_text(text) == text


class TestGetRefsAdded:
    def test_tracks_refs_added_since_last_check(self):
        cm = CitationManager()
        cm.add_ref("a.pdf", 1, "A")
        cm.add_ref("b.pdf", 2, "B")
        added = cm.get_refs_added()
        assert added == ["REF_1", "REF_2"]

    def test_resets_after_get(self):
        cm = CitationManager()
        cm.add_ref("a.pdf", 1, "A")
        cm.get_refs_added()  # clears the tracking
        cm.add_ref("b.pdf", 2, "B")
        added = cm.get_refs_added()
        assert added == ["REF_2"]


class TestPerInteraction:
    def test_new_manager_starts_fresh(self):
        cm1 = CitationManager()
        cm1.add_ref("report.pdf", 1, "First")
        cm2 = CitationManager()
        ref = cm2.add_ref("other.pdf", 1, "Second")
        assert ref == "[REF_1]"  # starts at 1 again
