from __future__ import annotations
from datetime import datetime, timezone
from enum import Enum
from dataclasses import dataclass


class Checkpoint(str,Enum):
    TYRE_BUILDING = "TYRE_BUILDING"
    CURING = "CURING"
    QUALITY_INSPECTION = "QUALITY_INSPECTION"
    WAREHOUSE = "WAREHOUSE"


@dataclass(frozen=True,slots=True)
class Tag:
    epc: str
    tyre_id: str
    description: str = ""

    def __post_init__(self) -> None:
        normalized = self.epc.replace(" ", "").upper()
        if not normalized or len(normalized) % 2 or any(c not in "0123456789ABCDEF" for c in normalized):
            raise ValueError("EPC must be a non-empty, even-length hexadecimal string")
        if not self.tyre_id.strip():
            raise ValueError("tyre_id cannot be empty")
        object.__setattr__(self, "epc", normalized)

@dataclass(frozen=True,slots=True)
class Observation:
    epc: str
    rssi_dbm: float
    antenna_id: int
    reader_id: str
    station_id: Checkpoint
    timestamp: datetime

    def __post_init__(self) -> None:
        if self.antenna_id < 1:
            raise ValueError("antenna_id must be positive")
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")

    @classmethod
    def now(cls, *, epc: str, rssi_dbm: float, antenna_id: int, reader_id: str, station_id: Checkpoint) -> "Observation":
        return cls(epc, rssi_dbm, antenna_id, reader_id, station_id, datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, str | int | float]:
        return {
            "epc": self.epc,
            "rssi_dbm": round(self.rssi_dbm, 1),
            "antenna_id": self.antenna_id,
            "reader_id": self.reader_id,
            "station_id": self.station_id.value,
            "timestamp": self.timestamp.isoformat(),
        }