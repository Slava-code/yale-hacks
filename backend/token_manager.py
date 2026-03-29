"""
Ephemeral token mapping system for PHI de-identification.

Spec: docs/interfaces.md §5, docs/backend.md §3.

Each TokenMapping is created per-interaction and destroyed after rehydration.
Tokens are deterministic (same value → same token within one mapping).
"""

from __future__ import annotations

from datetime import datetime, date
from dateutil.relativedelta import relativedelta


VALID_TYPES = {"PATIENT", "PROVIDER", "FAMILY", "MRN", "DATE", "LOCATION", "CONTACT"}

# Maps PHI type → human-readable category for token_summary
SUMMARY_LABELS = {
    "PATIENT": "patient_name",
    "PROVIDER": "provider_name",
    "FAMILY": "family_member",
    "MRN": "mrn",
    "DATE": "date",
    "LOCATION": "location",
    "CONTACT": "contact_info",
}


class TokenMapping:
    """Ephemeral per-interaction token mapping.

    Usage:
        tm = TokenMapping()
        tm.add("John Smith", "PATIENT")  # → "[PATIENT_1]"
        redacted = tm.apply("John Smith has headaches")  # → "[PATIENT_1] has headaches"
        restored = tm.rehydrate(redacted)  # → "John Smith has headaches"
        tm.destroy()
    """

    def __init__(self):
        self._counters: dict[str, int] = {}
        self._value_to_token: dict[str, str] = {}  # real_value → "[TYPE_N]"
        self._token_to_value: dict[str, str] = {}  # "[TYPE_N]" → real_value
        self._token_to_type: dict[str, str] = {}   # "[TYPE_N]" → TYPE
        self._date_relatives: dict[str, str] = {}   # date_string → relative description

    def add(self, real_value: str, phi_type: str) -> str:
        """Register a PHI value and return its token.

        Same value always returns the same token within this mapping.
        """
        if phi_type not in VALID_TYPES:
            raise ValueError(f"Invalid PHI type: {phi_type}. Must be one of {VALID_TYPES}")

        if not real_value or not real_value.strip():
            return ""

        if real_value in self._value_to_token:
            return self._value_to_token[real_value]

        self._counters[phi_type] = self._counters.get(phi_type, 0) + 1
        token = f"[{phi_type}_{self._counters[phi_type]}]"

        self._value_to_token[real_value] = token
        self._token_to_value[token] = real_value
        self._token_to_type[token] = phi_type

        return token

    def add_date(self, date_string: str) -> tuple[str, str]:
        """Register a date and return (token, relative_description).

        Converts exact dates to relative descriptions like "approximately 10 months ago".
        """
        if date_string in self._date_relatives:
            token = self._value_to_token[date_string]
            return token, self._date_relatives[date_string]

        relative = self._date_to_relative(date_string)
        token = self.add(date_string, "DATE")
        self._date_relatives[date_string] = relative

        return token, relative

    def apply(self, text: str) -> str:
        """Replace all registered PHI values in text with their tokens.

        Replaces longer values first to avoid partial matches.
        """
        result = text
        # Sort by length descending so "Dr. Sarah Chen" is replaced before "Sarah"
        for value, token in sorted(
            self._value_to_token.items(), key=lambda x: len(x[0]), reverse=True
        ):
            result = result.replace(value, token)
        return result

    def rehydrate(self, text: str) -> str:
        """Replace all tokens in text with their real values."""
        result = text
        for token, value in self._token_to_value.items():
            result = result.replace(token, value)
        return result

    def redact_node_fields(
        self, fields: dict, phi_type_map: dict[str, str]
    ) -> dict:
        """Redact a graph node's fields based on PHI tags.

        Args:
            fields: {field_name: {"value": ..., "phi": bool}}
            phi_type_map: {field_name: PHI_TYPE} for fields that are PHI

        Returns:
            Flat dict {field_name: value_or_token}
        """
        result = {}
        for field_name, field_data in fields.items():
            value = field_data["value"]
            is_phi = field_data.get("phi", False)

            if is_phi and field_name in phi_type_map:
                result[field_name] = self.add(str(value), phi_type_map[field_name])
            else:
                result[field_name] = value

        return result

    def get_summary(self) -> dict[str, str]:
        """Return {token_key: phi_category} for the deidentified_query SSE event.

        Returns keys without brackets, e.g. "PATIENT_1" not "[PATIENT_1]".
        Values are human-readable category labels.
        """
        summary = {}
        for token, phi_type in self._token_to_type.items():
            # Strip brackets: "[PATIENT_1]" → "PATIENT_1"
            key = token[1:-1]
            summary[key] = SUMMARY_LABELS.get(phi_type, phi_type.lower())
        return summary

    def destroy(self):
        """Clear all mappings. Called after rehydration."""
        self._counters.clear()
        self._value_to_token.clear()
        self._token_to_value.clear()
        self._token_to_type.clear()
        self._date_relatives.clear()

    @staticmethod
    def _date_to_relative(date_string: str) -> str:
        """Convert a date string to a relative description."""
        today = date.today()

        try:
            parsed = datetime.strptime(date_string, "%Y-%m-%d").date()
        except ValueError:
            try:
                parsed = datetime.strptime(date_string, "%B %d, %Y").date()
            except ValueError:
                return f"approximately {date_string}"

        delta = relativedelta(today, parsed)

        if delta.years > 0:
            unit = "year" if delta.years == 1 else "years"
            return f"approximately {delta.years} {unit} ago"
        elif delta.months > 0:
            unit = "month" if delta.months == 1 else "months"
            return f"approximately {delta.months} {unit} ago"
        elif delta.days > 0:
            unit = "day" if delta.days == 1 else "days"
            return f"approximately {delta.days} {unit} ago"
        else:
            return "today"
