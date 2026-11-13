from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

from .models import Checkpoint, Observation, Tag
from .quality_inspection import InspectionResult


class SQLiteStore:
    """Persist registered tyre tags and their checkpoint observations."""

    def __init__(self, database_path: str | Path) -> None:
        self.connection = sqlite3.connect(database_path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        schema_path = Path(__file__).resolve().parents[1] / "database" / "schema.sql"
        existing = self.connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'observations'"
        ).fetchone()
        if existing is not None:
            columns = {row["name"] for row in self.connection.execute("PRAGMA table_info(observations)")}
            if "event_id" not in columns:
                self.connection.execute("ALTER TABLE observations ADD COLUMN event_id TEXT")
            self.connection.execute(
                "UPDATE observations SET event_id = 'legacy-' || observation_id WHERE event_id IS NULL OR event_id = ''"
            )
            self.connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_observations_event_id ON observations(event_id)"
            )
        self.connection.executescript(schema_path.read_text(encoding="utf-8"))
        self.connection.commit()

    def register_tag(self, tag: Tag) -> None:
        existing = self.connection.execute(
            "SELECT epc, tyre_id FROM tyre_tags WHERE epc = ? OR tyre_id = ?",
            (tag.epc, tag.tyre_id),
        ).fetchone()
        if existing is not None:
            if existing["epc"] != tag.epc or existing["tyre_id"] != tag.tyre_id:
                raise ValueError("EPC and tyre_id must remain a one-to-one mapping")
            self.connection.execute(
                "UPDATE tyre_tags SET description = ? WHERE epc = ?",
                (tag.description, tag.epc),
            )
        else:
            self.connection.execute(
                "INSERT INTO tyre_tags (epc, tyre_id, description) VALUES (?, ?, ?)",
                (tag.epc, tag.tyre_id, tag.description),
            )
        self.connection.commit()

    def record_observation(self, observation: Observation) -> None:
        reader = self.connection.execute(
            "SELECT station_id FROM readers WHERE reader_id = ?",
            (observation.reader_id,),
        ).fetchone()
        if reader is None:
            self.connection.execute(
                "INSERT INTO readers (reader_id, station_id) VALUES (?, ?)",
                (observation.reader_id, observation.station_id.value),
            )
        elif reader["station_id"] != observation.station_id.value:
            raise ValueError("reader_id is already assigned to a different station")
        self.connection.execute(
            """INSERT OR IGNORE INTO reader_antennas (reader_id, antenna_id)
               VALUES (?, ?)""",
            (observation.reader_id, observation.antenna_id),
        )
        self.connection.execute(
            """INSERT INTO observations
               (event_id, epc, rssi_dbm, antenna_id, reader_id, station_id, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                uuid.uuid4().hex,
                observation.epc,
                observation.rssi_dbm,
                observation.antenna_id,
                observation.reader_id,
                observation.station_id.value,
                observation.timestamp.isoformat(),
            ),
        )
        self.connection.commit()

    def record_quality_inspection(self, epc: str, result: InspectionResult) -> None:
        self.connection.execute(
            """INSERT INTO quality_inspections
               (epc, passed, defect_code, inspected_at)
               VALUES (?, ?, ?, ?)""",
            (epc, int(result.passed), result.defect_code, result.inspected_at.isoformat()),
        )
        self.connection.commit()

    def history_for(self, epc: str) -> tuple[Observation, ...]:
        rows = self.connection.execute(
            """SELECT epc, rssi_dbm, antenna_id, reader_id, station_id, timestamp
               FROM observations WHERE epc = ? ORDER BY timestamp, observation_id""",
            (epc.replace(" ", "").upper(),),
        ).fetchall()
        return tuple(
            Observation(
                epc=row["epc"],
                rssi_dbm=row["rssi_dbm"],
                antenna_id=row["antenna_id"],
                reader_id=row["reader_id"],
                station_id=Checkpoint(row["station_id"]),
                timestamp=datetime.fromisoformat(row["timestamp"]),
            )
            for row in rows
        )

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> SQLiteStore:
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.close()
