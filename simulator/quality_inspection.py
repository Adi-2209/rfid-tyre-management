from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True, slots=True)
class InspectionResult:
    tyre_id: str
    passed: bool
    defect_code: str | None
    inspected_at: datetime


class SimulatedQualityInspector:
    """Generate reproducible sample inspection outcomes for the demo."""

    _DEFECT_CODES = ("TREAD_WEAR", "SIDEWALL_MARK", "DIMENSION_CHECK")

    def __init__(self, *, pass_probability: float = 0.9, seed: int | None = None) -> None:
        if not 0 <= pass_probability <= 1:
            raise ValueError("pass_probability must be between 0 and 1")
        self.pass_probability = pass_probability
        self._random = random.Random(seed)

    def inspect(self, tyre_id: str) -> InspectionResult:
        if not tyre_id.strip():
            raise ValueError("tyre_id cannot be empty")
        passed = self._random.random() < self.pass_probability
        defect = None if passed else self._random.choice(self._DEFECT_CODES)
        return InspectionResult(
            tyre_id=tyre_id,
            passed=passed,
            defect_code=defect,
            inspected_at=datetime.now(timezone.utc),
        )
