"""Text-only code values for the current ABB ACS580 fault-table format."""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class FaultCode:
    """Preserve the original spelling alongside a conservative comparison value.

    A matching shape does not prove that a code exists or identify its model,
    firmware scope or meaning. The caller must supply the source context.
    """

    raw_code: str
    normalized_code: str

    @classmethod
    def from_raw(cls, raw: str) -> "FaultCode":
        if not isinstance(raw, str) or re.fullmatch(r"[0-9A-Fa-f]{4}", raw.strip()) is None:
            raise ValueError("Fault code must be a four-character ASCII hexadecimal string")
        return cls(raw_code=raw, normalized_code=raw.strip().upper())
