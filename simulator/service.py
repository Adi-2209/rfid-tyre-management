from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .models import Observation
from .tracker import CheckpointTracker
from .storage import SQLiteStore
from .virtual_tags import TagRegistry


@dataclass(frozen=True, slots=True)
class IngestResult:
    accepted: int
    stale: int
    unknown_epcs: tuple[str, ...]


class TrackingService:
    """Apply reader observations to registered tyres and their checkpoint histories."""

    def __init__(self, registry: TagRegistry, tracker: CheckpointTracker, store: SQLiteStore | None = None) -> None:
        self.registry = registry
        self.tracker = tracker
        self.store = store

    def ingest(self, observations: Iterable[Observation]) -> IngestResult:
        accepted = 0
        stale = 0
        unknown: set[str] = set()

        for observation in observations:
            if self.registry.get_by_epc(observation.epc) is None:
                unknown.add(observation.epc)
                continue
            if self.tracker.record(observation):
                if self.store is not None:
                    self.store.record_observation(observation)
                accepted += 1
            else:
                stale += 1

        return IngestResult(
            accepted=accepted,
            stale=stale,
            unknown_epcs=tuple(sorted(unknown)),
        )
