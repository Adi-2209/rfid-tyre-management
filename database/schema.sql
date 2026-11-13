-- RFID tyre management schema (SQLite 3)
-- Stations are seeded below; EPC and tyre_id are a one-to-one mapping.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS stations (
    station_id TEXT PRIMARY KEY,
    station_name TEXT NOT NULL UNIQUE,
    sequence_no INTEGER NOT NULL UNIQUE CHECK (sequence_no > 0),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
);

INSERT OR IGNORE INTO stations (station_id, station_name, sequence_no) VALUES
    ('TYRE_BUILDING', 'Tyre Building', 1),
    ('CURING', 'Curing', 2),
    ('QUALITY_INSPECTION', 'Quality Inspection', 3),
    ('WAREHOUSE', 'Warehouse', 4);

CREATE TABLE IF NOT EXISTS tyre_tags (
    epc TEXT PRIMARY KEY,
    tyre_id TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL DEFAULT '',
    registered_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    CHECK (length(epc) > 0),
    CHECK (epc = upper(replace(epc, ' ', ''))),
    CHECK (length(epc) % 2 = 0),
    CHECK (epc NOT GLOB '*[^0-9A-F]*')
);

CREATE TABLE IF NOT EXISTS readers (
    reader_id TEXT PRIMARY KEY,
    station_id TEXT NOT NULL REFERENCES stations(station_id),
    reader_type TEXT NOT NULL DEFAULT 'UHF_RFID',
    location TEXT NOT NULL DEFAULT '',
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    last_seen_at TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS reader_antennas (
    reader_id TEXT NOT NULL REFERENCES readers(reader_id) ON DELETE CASCADE,
    antenna_id INTEGER NOT NULL CHECK (antenna_id > 0),
    description TEXT NOT NULL DEFAULT '',
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    PRIMARY KEY (reader_id, antenna_id)
);

-- Raw read events are append-only: repeated reads are useful signal data.
CREATE TABLE IF NOT EXISTS observations (
    observation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL,
    epc TEXT NOT NULL REFERENCES tyre_tags(epc),
    reader_id TEXT NOT NULL,
    antenna_id INTEGER NOT NULL CHECK (antenna_id > 0),
    station_id TEXT NOT NULL REFERENCES stations(station_id),
    rssi_dbm REAL NOT NULL CHECK (rssi_dbm BETWEEN -150 AND 50),
    timestamp TEXT NOT NULL,
    FOREIGN KEY (reader_id, antenna_id)
        REFERENCES reader_antennas(reader_id, antenna_id)
);

CREATE TABLE IF NOT EXISTS quality_inspections (
    inspection_id INTEGER PRIMARY KEY AUTOINCREMENT,
    epc TEXT NOT NULL REFERENCES tyre_tags(epc),
    station_id TEXT NOT NULL DEFAULT 'QUALITY_INSPECTION'
        REFERENCES stations(station_id),
    passed INTEGER NOT NULL CHECK (passed IN (0, 1)),
    defect_code TEXT,
    notes TEXT NOT NULL DEFAULT '',
    inspected_at TEXT NOT NULL,
    inspector_id TEXT NOT NULL DEFAULT 'SIMULATED',
    CHECK (station_id = 'QUALITY_INSPECTION'),
    CHECK ((passed = 1 AND defect_code IS NULL) OR (passed = 0 AND defect_code IS NOT NULL))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_observations_event_id
    ON observations(event_id);

CREATE INDEX IF NOT EXISTS idx_observations_epc_time
    ON observations(epc, timestamp, observation_id);

CREATE INDEX IF NOT EXISTS idx_observations_station_time
    ON observations(station_id, timestamp);

CREATE INDEX IF NOT EXISTS idx_observations_reader_time
    ON observations(reader_id, timestamp);

CREATE INDEX IF NOT EXISTS idx_quality_inspections_epc_time
    ON quality_inspections(epc, inspected_at, inspection_id);

CREATE INDEX IF NOT EXISTS idx_quality_inspections_result
    ON quality_inspections(passed, inspected_at);

-- A reader's configured station must match every observation it emits.
CREATE TRIGGER IF NOT EXISTS trg_observation_reader_station
BEFORE INSERT ON observations
WHEN (SELECT station_id FROM readers WHERE reader_id = NEW.reader_id) <> NEW.station_id
BEGIN
    SELECT RAISE(ABORT, 'observation station does not match reader station');
END;

-- A tyre may enter the warehouse only after its latest quality inspection passed.
CREATE TRIGGER IF NOT EXISTS trg_warehouse_requires_pass
BEFORE INSERT ON observations
WHEN NEW.station_id = 'WAREHOUSE' AND NOT EXISTS (
    SELECT 1
    FROM quality_inspections AS qi
    WHERE qi.epc = NEW.epc
      AND qi.passed = 1
      AND julianday(qi.inspected_at) <= julianday(NEW.timestamp)
      AND NOT EXISTS (
          SELECT 1
          FROM quality_inspections AS newer
          WHERE newer.epc = qi.epc
            AND julianday(newer.inspected_at) > julianday(qi.inspected_at)
      )
)
BEGIN
    SELECT RAISE(ABORT, 'latest quality inspection must pass before warehouse entry');
END;
