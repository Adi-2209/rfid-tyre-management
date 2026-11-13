from __future__ import annotations

import random
import time
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Protocol, Sequence

from .models import Checkpoint, Observation, Tag


class Reader(Protocol):
    """Adapter boundary. A physical UHF reader can implement this interface."""

    def read(self, tags: Sequence[Tag], *, duration_seconds: float = 1.0) -> list[Observation]: ...


@dataclass(frozen=True, slots=True)
class SimulationScenario:
    name: str = "normal_passage"
    reads_per_tag: int = 5
    rssi_mean_dbm: float = -48.0
    rssi_stddev_db: float = 4.0
    read_interval_seconds: float = 0.12
    missed_read_probability: float = 0.08
    antenna_ids: tuple[int, ...] = (1, 2)
    seed: int | None = None

    def __post_init__(self) -> None:
        if self.reads_per_tag < 1 or self.rssi_stddev_db < 0 or self.read_interval_seconds < 0:
            raise ValueError("reads_per_tag must be positive; RSSI deviation and interval cannot be negative")
        if not 0 <= self.missed_read_probability <= 1:
            raise ValueError("missed_read_probability must be between 0 and 1")
        if not self.antenna_ids or any(antenna < 1 for antenna in self.antenna_ids):
            raise ValueError("antenna_ids must contain positive IDs")

    @classmethod
    def named(cls, name: str, *, seed: int | None = None) -> "SimulationScenario":
        presets = {
            "normal_passage": cls(),
            "weak_signal": cls(name="weak_signal", rssi_mean_dbm=-68.0, rssi_stddev_db=5.5, missed_read_probability=0.25),
            "fast_passage": cls(name="fast_passage", reads_per_tag=3, read_interval_seconds=0.04),
            "noisy_environment": cls(name="noisy_environment", rssi_mean_dbm=-53.0, rssi_stddev_db=9.0, missed_read_probability=0.18),
            "tag_missed": cls(name="tag_missed", reads_per_tag=5, missed_read_probability=1.0),
        }
        try:
            preset = presets[name]
        except KeyError as exc:
            raise ValueError(f"Unknown scenario {name!r}; choose from {', '.join(presets)}") from exc
        return replace(preset, seed=seed)


class SimulatedReader:
    def __init__(self, reader_id: str, station_id: Checkpoint, scenario: SimulationScenario | None = None) -> None:
        if not reader_id.strip():
            raise ValueError("reader_id cannot be empty")
        self.reader_id = reader_id
        self.station_id = station_id
        self.scenario = scenario or SimulationScenario()
        self._random = random.Random(self.scenario.seed)

    def read(self, tags: Sequence[Tag], *, duration_seconds: float = 1.0) -> list[Observation]:
        """Emit repeat reads over a passage window; sleep only when interval is nonzero."""
        if duration_seconds < 0:
            raise ValueError("duration_seconds cannot be negative")
        scenario = self.scenario
        total_slots = scenario.reads_per_tag * len(tags)
        interval = min(scenario.read_interval_seconds, duration_seconds / max(total_slots, 1))
        observations: list[Observation] = []
        start = datetime.now(timezone.utc)
        for tag_index, tag in enumerate(tags):
            for read_index in range(scenario.reads_per_tag):
                if self._random.random() >= scenario.missed_read_probability:
                    elapsed = (tag_index * scenario.reads_per_tag + read_index) * interval
                    observations.append(Observation(
                        epc=tag.epc,
                        rssi_dbm=self._random.gauss(scenario.rssi_mean_dbm, scenario.rssi_stddev_db),
                        antenna_id=self._random.choice(scenario.antenna_ids),
                        reader_id=self.reader_id,
                        station_id=self.station_id,
                        timestamp=start + timedelta(seconds=elapsed),
                    ))
                if interval:
                    time.sleep(interval)
        return observations
