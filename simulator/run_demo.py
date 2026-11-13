from __future__ import annotations

from .models import Checkpoint, Tag
from .quality_inspection import SimulatedQualityInspector
from .service import TrackingService
from .storage import SQLiteStore
from .tracker import CheckpointTracker
from .virtual_reader import SimulatedReader, SimulationScenario
from .virtual_tags import TagRegistry
from pathlib import Path


def main() -> None:
    registry = TagRegistry()
    tags = (
        Tag(epc="E2000017221101441890ABCD", tyre_id="TYRE-001", description="Passenger tyre"),
        Tag(epc="E2000017221101441890ABCE", tyre_id="TYRE-002", description="Passenger tyre"),
    )
    for tag in tags:
        registry.register(tag)

    tracker = CheckpointTracker()
    database_path = Path(__file__).resolve().parents[1] / "database" / "rfid_tyre.db"
    store = SQLiteStore(database_path)
    for tag in tags:
        store.register_tag(tag)
    service = TrackingService(registry, tracker, store)
    inspector = SimulatedQualityInspector(pass_probability=0.8, seed=1)
    warehouse_eligible = []
    scenario = SimulationScenario(
        reads_per_tag=2,
        read_interval_seconds=0.01,
        missed_read_probability=0,
        seed=7,
    )

    for station in Checkpoint:
        station_tags = warehouse_eligible if station is Checkpoint.WAREHOUSE else tags
        reader = SimulatedReader(
            reader_id=f"SIM-{station.value}",
            station_id=station,
            scenario=scenario,
        )
        observations = reader.read(station_tags, duration_seconds=0.1)
        result = service.ingest(observations)
        print(
            f"{station.value}: accepted={result.accepted}, "
            f"stale={result.stale}, unknown={len(result.unknown_epcs)}"
        )
        if station is Checkpoint.QUALITY_INSPECTION:
            for tag in tags:
                inspection = inspector.inspect(tag.tyre_id)
                store.record_quality_inspection(tag.epc, inspection)
                verdict = "PASS" if inspection.passed else f"FAIL ({inspection.defect_code})"
                print(f"  {tag.tyre_id} quality: {verdict}")
                if inspection.passed:
                    warehouse_eligible.append(tag)

    print("\nTyre checkpoint histories:")
    for tag in tags:
        stations = []
        for observation in tracker.history_for(tag.epc):
            if not stations or stations[-1] != observation.station_id:
                stations.append(observation.station_id)
        route = " -> ".join(station.value for station in stations)
        print(f"{tag.tyre_id}: {route}")
        persisted = store.history_for(tag.epc)
        print(f"  stored observations: {len(persisted)}")

    store.close()


if __name__ == "__main__":
    main()
