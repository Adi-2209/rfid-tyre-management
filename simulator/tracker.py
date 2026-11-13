from __future__ import annotations

from .models import Observation


class CheckpointTracker:
    """Keep an ordered checkpoint history for each EPC."""

    def __init__(self) -> None:
        self._history: dict[str, list[Observation]] = {}

    def record(self, observation: Observation) -> bool:
        """Append a newer observation; return False for stale or duplicate reads."""
        history = self._history.setdefault(observation.epc, [])
        if history and observation.timestamp <= history[-1].timestamp:
            return False
        history.append(observation)
        return True

    def latest_for(self, epc: str) -> Observation | None:
        history = self._history.get(self._normalize_epc(epc), [])
        return history[-1] if history else None

    def history_for(self, epc: str) -> tuple[Observation, ...]:
        """Return accepted observations in timestamp order."""
        return tuple(self._history.get(self._normalize_epc(epc), ()))

    def snapshot(self) -> dict[str, Observation]:
        """Return each EPC's latest accepted observation."""
        return {
            epc: history[-1]
            for epc, history in self._history.items()
            if history
        }

    @staticmethod
    def _normalize_epc(epc: str) -> str:
        return epc.replace(" ", "").upper()

    def __len__(self) -> int:
        """Return the number of tracked EPCs."""
        return len(self._history)
