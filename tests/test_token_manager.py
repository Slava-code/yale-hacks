"""Tests for the ephemeral token mapping system."""

import pytest
from backend.token_manager import TokenMapping


class TestTokenCreation:
    def test_add_patient_returns_correct_format(self):
        tm = TokenMapping()
        token = tm.add("John Smith", "PATIENT")
        assert token == "[PATIENT_1]"

    def test_add_increments_counter(self):
        tm = TokenMapping()
        t1 = tm.add("John Smith", "PATIENT")
        t2 = tm.add("Maria Garcia", "PATIENT")
        assert t1 == "[PATIENT_1]"
        assert t2 == "[PATIENT_2]"

    def test_same_value_returns_same_token(self):
        tm = TokenMapping()
        t1 = tm.add("John Smith", "PATIENT")
        t2 = tm.add("John Smith", "PATIENT")
        assert t1 == t2 == "[PATIENT_1]"

    def test_all_token_types(self):
        tm = TokenMapping()
        assert tm.add("John Smith", "PATIENT") == "[PATIENT_1]"
        assert tm.add("Dr. Chen", "PROVIDER") == "[PROVIDER_1]"
        assert tm.add("Mary Smith", "FAMILY") == "[FAMILY_1]"
        assert tm.add("MRN-78234", "MRN") == "[MRN_1]"
        assert tm.add("Springfield", "LOCATION") == "[LOCATION_1]"
        assert tm.add("555-0142", "CONTACT") == "[CONTACT_1]"

    def test_invalid_type_raises(self):
        tm = TokenMapping()
        with pytest.raises(ValueError):
            tm.add("something", "INVALID_TYPE")


class TestApply:
    def test_replaces_phi_in_text(self):
        tm = TokenMapping()
        tm.add("John Smith", "PATIENT")
        tm.add("Dr. Sarah Chen", "PROVIDER")
        text = "John Smith was seen by Dr. Sarah Chen for headaches."
        result = tm.apply(text)
        assert result == "[PATIENT_1] was seen by [PROVIDER_1] for headaches."

    def test_preserves_clinical_info(self):
        tm = TokenMapping()
        tm.add("John Smith", "PATIENT")
        text = "John Smith, 31, male, WBC 3.2, Hemoglobin 11.8."
        result = tm.apply(text)
        assert "[PATIENT_1]" in result
        assert "31" in result
        assert "male" in result
        assert "WBC 3.2" in result
        assert "Hemoglobin 11.8" in result

    def test_replaces_multiple_occurrences(self):
        tm = TokenMapping()
        tm.add("John Smith", "PATIENT")
        text = "John Smith came in. We examined John Smith and found nothing."
        result = tm.apply(text)
        assert result == "[PATIENT_1] came in. We examined [PATIENT_1] and found nothing."

    def test_no_phi_returns_unchanged(self):
        tm = TokenMapping()
        text = "Patient presents with headaches and fatigue."
        result = tm.apply(text)
        assert result == text


class TestRehydrate:
    def test_restores_original_text(self):
        tm = TokenMapping()
        tm.add("John Smith", "PATIENT")
        tm.add("Dr. Sarah Chen", "PROVIDER")
        tm.add("Springfield General", "LOCATION")
        original = "John Smith was seen by Dr. Sarah Chen at Springfield General."
        redacted = tm.apply(original)
        restored = tm.rehydrate(redacted)
        assert restored == original

    def test_roundtrip_with_all_types(self):
        tm = TokenMapping()
        tm.add("John Smith", "PATIENT")
        tm.add("Dr. Chen", "PROVIDER")
        tm.add("Mary Smith", "FAMILY")
        tm.add("MRN-78234", "MRN")
        tm.add("Springfield", "LOCATION")
        tm.add("555-0142", "CONTACT")
        original = "John Smith (MRN-78234) seen at Springfield. Dr. Chen consulted. Emergency contact: Mary Smith, 555-0142."
        redacted = tm.apply(original)
        assert "John Smith" not in redacted
        assert "MRN-78234" not in redacted
        assert "Springfield" not in redacted
        restored = tm.rehydrate(redacted)
        assert restored == original


class TestDateHandling:
    def test_date_to_relative(self):
        tm = TokenMapping()
        # The add_date method should convert to relative and store mapping
        token, relative = tm.add_date("2025-10-15")
        assert token == "[DATE_1]"
        assert "ago" in relative or "approximately" in relative

    def test_multiple_dates(self):
        tm = TokenMapping()
        t1, _ = tm.add_date("2025-06-10")
        t2, _ = tm.add_date("2025-10-15")
        assert t1 == "[DATE_1]"
        assert t2 == "[DATE_2]"

    def test_same_date_same_token(self):
        tm = TokenMapping()
        t1, r1 = tm.add_date("2025-10-15")
        t2, r2 = tm.add_date("2025-10-15")
        assert t1 == t2
        assert r1 == r2


class TestPHITagAware:
    def test_redact_node_fields(self):
        """Given a graph node with phi-tagged fields, redact only phi=true fields."""
        tm = TokenMapping()
        fields = {
            "name": {"value": "John Smith", "phi": True},
            "age": {"value": 31, "phi": False},
            "sex": {"value": "male", "phi": False},
            "mrn": {"value": "MRN-78234", "phi": True},
        }
        phi_type_map = {"name": "PATIENT", "mrn": "MRN"}
        redacted_fields = tm.redact_node_fields(fields, phi_type_map)
        assert redacted_fields["name"] == "[PATIENT_1]"
        assert redacted_fields["age"] == 31
        assert redacted_fields["sex"] == "male"
        assert redacted_fields["mrn"] == "[MRN_1]"


class TestGetSummary:
    def test_summary_returns_type_not_value(self):
        """token_summary should map token -> phi category, NOT the real value."""
        tm = TokenMapping()
        tm.add("John Smith", "PATIENT")
        tm.add("MRN-78234", "MRN")
        summary = tm.get_summary()
        assert summary == {"PATIENT_1": "patient_name", "MRN_1": "mrn"}


class TestDestroy:
    def test_destroy_clears_mapping(self):
        tm = TokenMapping()
        tm.add("John Smith", "PATIENT")
        tm.destroy()
        # After destroy, rehydrate should not restore anything
        result = tm.rehydrate("[PATIENT_1]")
        assert result == "[PATIENT_1]"

    def test_destroy_clears_all_state(self):
        tm = TokenMapping()
        tm.add("John Smith", "PATIENT")
        tm.add_date("2025-10-15")
        tm.destroy()
        summary = tm.get_summary()
        assert summary == {}
