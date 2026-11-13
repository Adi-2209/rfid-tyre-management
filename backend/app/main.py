from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from simulator.models import Checkpoint, Tag


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = PROJECT_ROOT / "database" / "schema.sql"
DATABASE_PATH = Path(
    os.environ.get("RFID_DATABASE_PATH", PROJECT_ROOT / "database" / "rfid_tyre.db")
)

app = FastAPI(title="RFID Tyre Management API", version="0.2.0")
PASSWORD_ITERATIONS = 310_000
SESSION_HOURS = 12


class TagRegistration(BaseModel):
    epc: str = Field(min_length=1)
    tyre_id: str = Field(min_length=1)
    description: str = ""


class ObservationInput(BaseModel):
    epc: str = Field(min_length=1)
    event_id: str | None = Field(default=None, min_length=1, max_length=64)
    reader_id: str = Field(min_length=1)
    antenna_id: int = Field(ge=1)
    station_id: Checkpoint
    rssi_dbm: float = Field(ge=-150, le=50)
    timestamp: datetime


class LoginInput(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class AdminSetupInput(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=12, max_length=256)

class ReaderHeartbeatInput(BaseModel):
    reader_id: str = Field(min_length=1, max_length=64)
    station_id: Checkpoint

class InspectionInput(BaseModel):
    passed: bool
    defect_code: str | None = None
    notes: str = ""
    inspector_id: str = "SIMULATED"
    inspected_at: datetime | None = None


@contextmanager
def database() -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


@app.on_event("startup")
def initialize_database() -> None:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not SCHEMA_PATH.exists():
        raise RuntimeError(f"Database schema not found: {SCHEMA_PATH}")
    
    with database() as connection:

        reader_columns = {row["name"] for row in connection.execute("PRAGMA table_info(readers)")}
        if reader_columns and "last_seen_at" not in reader_columns:
            connection.execute("ALTER TABLE readers ADD COLUMN last_seen_at TEXT")

        observations_table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'observations'"
        ).fetchone()
        if observations_table is not None:
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(observations)")}
            if "event_id" not in columns:
                connection.execute("ALTER TABLE observations ADD COLUMN event_id TEXT")
            connection.execute(
                "UPDATE observations SET event_id = 'legacy-' || observation_id WHERE event_id IS NULL OR event_id = ''"
            )
            connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_observations_event_id ON observations(event_id)"
            )
        connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        connection.executescript(
            """CREATE TABLE IF NOT EXISTS app_users (
                   user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                   username TEXT NOT NULL UNIQUE,
                   password_salt TEXT NOT NULL,
                   password_hash TEXT NOT NULL,
                   created_at TEXT NOT NULL
               );
               CREATE TABLE IF NOT EXISTS app_sessions (
                   token_hash TEXT PRIMARY KEY,
                   user_id INTEGER NOT NULL REFERENCES app_users(user_id) ON DELETE CASCADE,
                   expires_at TEXT NOT NULL,
                   created_at TEXT NOT NULL
               );
               CREATE INDEX IF NOT EXISTS idx_app_sessions_expiry ON app_sessions(expires_at);"""
        )


def _password_hash(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS)


def _issue_session(connection: sqlite3.Connection, user_id: int) -> dict[str, str | int]:
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    expires = now + timedelta(hours=SESSION_HOURS)
    connection.execute(
        "INSERT INTO app_sessions (token_hash, user_id, expires_at, created_at) VALUES (?, ?, ?, ?)",
        (hashlib.sha256(token.encode()).hexdigest(), user_id, expires.isoformat(), now.isoformat()),
    )
    row = connection.execute("SELECT username FROM app_users WHERE user_id = ?", (user_id,)).fetchone()
    return {"access_token": token, "token_type": "bearer", "expires_at": expires.isoformat(), "username": row["username"]}


def require_user(authorization: str | None = Header(default=None)) -> dict[str, int | str]:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Sign in to continue", headers={"WWW-Authenticate": "Bearer"})
    token = authorization[7:].strip()
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    now = datetime.now(timezone.utc).isoformat()
    with database() as connection:
        row = connection.execute(
            """SELECT u.user_id, u.username FROM app_sessions s
               JOIN app_users u ON u.user_id = s.user_id
               WHERE s.token_hash = ? AND s.expires_at > ?""",
            (token_hash, now),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=401, detail="Session expired; sign in again", headers={"WWW-Authenticate": "Bearer"})
    return {"user_id": row["user_id"], "username": row["username"], "token_hash": token_hash}


def require_reader_or_user(
    authorization: str | None = Header(default=None),
    x_reader_key: str | None = Header(default=None),
) -> dict[str, int | str]:
    configured_key = os.environ.get("RFID_DEVICE_API_KEY", "")
    if configured_key and x_reader_key and hmac.compare_digest(x_reader_key, configured_key):
        return {"username": "reader", "user_id": 0}
    return require_user(authorization)


@app.get("/auth/status")
def auth_status() -> dict[str, bool]:
    with database() as connection:
        count = connection.execute("SELECT COUNT(*) AS count FROM app_users").fetchone()["count"]
    return {"setup_required": count == 0}


@app.post("/auth/setup", status_code=201)
def setup_admin(payload: AdminSetupInput) -> dict[str, str | int]:
    username = payload.username.strip()
    if len(username) < 3:
        raise HTTPException(status_code=422, detail="Username must contain at least 3 non-space characters")
    salt = secrets.token_bytes(16)
    digest = _password_hash(payload.password, salt)
    now = datetime.now(timezone.utc).isoformat()
    try:
        with database() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if connection.execute("SELECT 1 FROM app_users LIMIT 1").fetchone() is not None:
                raise HTTPException(status_code=409, detail="Admin setup is already complete")
            cursor = connection.execute(
                "INSERT INTO app_users (username, password_salt, password_hash, created_at) VALUES (?, ?, ?, ?)",
                (username, salt.hex(), digest.hex(), now),
            )
            if cursor.lastrowid is None:
                raise RuntimeError("SQLite did not return a user ID")
            return _issue_session(connection, cursor.lastrowid)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Username is already in use") from exc


@app.post("/auth/login")
def login(payload: LoginInput) -> dict[str, str | int]:
    with database() as connection:
        row = connection.execute(
            "SELECT user_id, username, password_salt, password_hash FROM app_users WHERE username = ?",
            (payload.username.strip(),),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=401, detail="Incorrect username or password")
        candidate = _password_hash(payload.password, bytes.fromhex(row["password_salt"]))
        if not hmac.compare_digest(candidate.hex(), row["password_hash"]):
            raise HTTPException(status_code=401, detail="Incorrect username or password")
        return _issue_session(connection, row["user_id"])


@app.get("/auth/me")
def current_user(user: dict[str, int | str] = Depends(require_user)) -> dict[str, str | int]:
    return {"user_id": user["user_id"], "username": user["username"]}


@app.post("/auth/logout")
def logout(user: dict[str, int | str] = Depends(require_user)) -> dict[str, str]:
    with database() as connection:
        connection.execute("DELETE FROM app_sessions WHERE token_hash = ?", (user["token_hash"],))
    return {"status": "signed out"}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

@app.post("/readers/heartbeat")
def reader_heartbeat(
    payload: ReaderHeartbeatInput,
    user: dict[str, int | str] = Depends(require_reader_or_user),
) -> dict[str, str]:
    station = payload.station_id.value
    datetime_now = datetime.now(timezone.utc).isoformat()
    with database() as connection:
        reader = connection.execute(
            "SELECT station_id FROM readers WHERE reader_id = ?",
            (payload.reader_id,),
        ).fetchone()
        if reader is None:
            connection.execute(
                "INSERT INTO readers (reader_id, station_id, last_seen_at) VALUES (?, ?, ?)",
                (payload.reader_id, station, datetime_now),
            )
        elif reader["station_id"] != station:
            raise HTTPException(
                status_code=409,
                detail="Reader is already assigned to a different station",
            )
        else:
            connection.execute(
                "UPDATE readers SET last_seen_at = ? WHERE reader_id = ?",
                (datetime_now, payload.reader_id),
            )
    return {"status": "ok", "reader_id": payload.reader_id, "station_id": station, "last_seen_at": datetime_now}

@app.get("/readers/status")
def reader_status(
    offline_after_seconds: int = Query(default=45, ge=15, le=300),
    user: dict[str, int | str] = Depends(require_user),
) -> dict[str, object]:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=offline_after_seconds)
    with database() as connection:
        rows = connection.execute(
            "SELECT reader_id, station_id, last_seen_at FROM readers ORDER BY reader_id"
        ).fetchall()
        readers = []
        for row in rows:
            last_seen = datetime.fromisoformat(row["last_seen_at"]) if row["last_seen_at"] else None
            if last_seen is not None and last_seen.tzinfo is None:
                last_seen = last_seen.replace(tzinfo=timezone.utc)
            readers.append({
                "reader_id":row["reader_id"],
                "station_id":row["station_id"],
                "last_seen_at": row["last_seen_at"],
                "online": last_seen is not None and last_seen >= cutoff,
            })
    return {"readers": readers, "offline_after_seconds": offline_after_seconds, "checked_at": now.isoformat()}

@app.get("/observations/recent")
def recent_observations(
    after_id: int = Query(default=0, ge=0),
    limit: int = Query(default=25, ge=1, le=100),
    user: dict[str, int | str] = Depends(require_user),
) -> dict[str, object]:
    with database() as connection:
        if after_id == 0:
            rows = connection.execute(
                """SELECT o.observation_id, o.event_id, o.epc, t.tyre_id, o.reader_id,
                          o.antenna_id, o.station_id, o.rssi_dbm, o.timestamp
                   FROM observations AS o
                   JOIN tyre_tags AS t ON t.epc = o.epc
                   ORDER BY o.observation_id DESC LIMIT ?""",
                (limit,),
            ).fetchall()
            rows = list(reversed(rows))
        else:
            rows = connection.execute(
                """SELECT o.observation_id, o.event_id, o.epc, t.tyre_id, o.reader_id,
                          o.antenna_id, o.station_id, o.rssi_dbm, o.timestamp
                   FROM observations AS o
                   JOIN tyre_tags AS t ON t.epc = o.epc
                   WHERE o.observation_id > ?
                   ORDER BY o.observation_id LIMIT ?""",
                (after_id, limit),
            ).fetchall()

    items = [dict(row) for row in rows]
    cursor = max((item["observation_id"] for item in items), default=after_id)
    return {"items": items, "cursor": cursor}

@app.post("/tags", status_code=201)
def register_tag(payload: TagRegistration, user: dict[str, int | str] = Depends(require_user)) -> dict[str, str]:
    try:
        tag = Tag(payload.epc, payload.tyre_id, payload.description)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        with database() as connection:
            connection.execute(
                "INSERT INTO tyre_tags (epc, tyre_id, description) VALUES (?, ?, ?)",
                (tag.epc, tag.tyre_id, tag.description),
            )
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail="EPC or tyre_id is already registered",
        ) from exc
    return {"epc": tag.epc, "tyre_id": tag.tyre_id, "description": tag.description}


@app.post("/observations", status_code=201)
def record_observation(payload: ObservationInput, response: Response, user: dict[str, int | str] = Depends(require_reader_or_user)) -> dict[str, int | str | bool]:
    if payload.timestamp.tzinfo is None or payload.timestamp.utcoffset() is None:
        raise HTTPException(status_code=422, detail="timestamp must include a timezone")
    epc = payload.epc.replace(" ", "").upper()
    station = payload.station_id.value
    event_id = payload.event_id or uuid.uuid4().hex
    duplicate = False

    try:
        with database() as connection:
            existing = connection.execute(
                """SELECT observation_id, epc, reader_id, antenna_id, station_id, rssi_dbm, timestamp
                   FROM observations WHERE event_id = ?""",
                (event_id,),
            ).fetchone()
            if existing is not None:
                same_event = (
                    existing["epc"] == epc
                    and existing["reader_id"] == payload.reader_id
                    and existing["antenna_id"] == payload.antenna_id
                    and existing["station_id"] == station
                    and existing["rssi_dbm"] == payload.rssi_dbm
                    and existing["timestamp"] == payload.timestamp.isoformat()
                )
                if not same_event:
                    raise HTTPException(status_code=409, detail="event_id was already used for a different observation")
                observation_id = existing["observation_id"]
                duplicate = True
            elif connection.execute(
                "SELECT 1 FROM tyre_tags WHERE epc = ?", (epc,)
            ).fetchone() is None:
                raise HTTPException(status_code=404, detail="Unknown EPC; register the tyre tag first")

            if not duplicate:
                reader = connection.execute(
                    "SELECT station_id FROM readers WHERE reader_id = ?",
                    (payload.reader_id,),
                ).fetchone()
                if reader is None:
                    connection.execute(
                        "INSERT INTO readers (reader_id, station_id, last_seen_at) VALUES (?, ?, ?)",
                        (payload.reader_id, station, datetime.now(timezone.utc).isoformat()),
                    )
                elif reader["station_id"] != station:
                    raise HTTPException(
                        status_code=409,
                        detail="Reader is already assigned to a different station",
                    )
                else:
                    connection.execute(
                        "UPDATE readers SET last_seen_at = ? WHERE reader_id = ?",
                        (datetime.now(timezone.utc).isoformat(), payload.reader_id),
                    )
    
                connection.execute(
                    "INSERT OR IGNORE INTO reader_antennas (reader_id, antenna_id) VALUES (?, ?)",
                    (payload.reader_id, payload.antenna_id),
                )
                cursor = connection.execute(
                    """INSERT INTO observations
                       (event_id, epc, reader_id, antenna_id, station_id, rssi_dbm, timestamp)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        event_id,
                        epc,
                        payload.reader_id,
                        payload.antenna_id,
                        station,
                        payload.rssi_dbm,
                        payload.timestamp.isoformat(),
                    ),
                )
                if cursor.lastrowid is None:
                    raise RuntimeError("SQLite did not return an observation ID")
                observation_id = cursor.lastrowid
    except sqlite3.IntegrityError as exc:
        message = str(exc)
        if "latest quality inspection" in message:
            raise HTTPException(status_code=409, detail=message) from exc
        raise HTTPException(status_code=422, detail=message) from exc

    if duplicate:
        response.status_code = 200
    return {
        "observation_id": observation_id,
        "event_id": event_id,
        "epc": epc,
        "station_id": station,
        "duplicate": duplicate,
    }


@app.post("/tyres/{tyre_id}/inspections", status_code=201)
def record_inspection(tyre_id: str, payload: InspectionInput, user: dict[str, int | str] = Depends(require_user)) -> dict[str, int | str | bool | None]:
    if payload.passed and payload.defect_code is not None:
        raise HTTPException(status_code=422, detail="A passing inspection cannot have a defect_code")
    if not payload.passed and not payload.defect_code:
        raise HTTPException(status_code=422, detail="A failed inspection requires a defect_code")

    inspected_at = payload.inspected_at or datetime.now(timezone.utc)
    if inspected_at.tzinfo is None or inspected_at.utcoffset() is None:
        raise HTTPException(status_code=422, detail="inspected_at must include a timezone")

    with database() as connection:
        tag = connection.execute(
            "SELECT epc FROM tyre_tags WHERE tyre_id = ?", (tyre_id,)
        ).fetchone()
        if tag is None:
            raise HTTPException(status_code=404, detail="Unknown tyre_id")
        reached_inspection = connection.execute(
            """SELECT 1 FROM observations
               WHERE epc = ? AND station_id = 'QUALITY_INSPECTION'
                 AND julianday(timestamp) <= julianday(?)
               LIMIT 1""",
            (tag["epc"], inspected_at.isoformat()),
        ).fetchone()
        if reached_inspection is None:
            raise HTTPException(
                status_code=409,
                detail="Tyre must be observed at quality inspection before recording a result",
            )
        cursor = connection.execute(
            """INSERT INTO quality_inspections
               (epc, passed, defect_code, notes, inspected_at, inspector_id)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                tag["epc"],
                int(payload.passed),
                payload.defect_code,
                payload.notes,
                inspected_at.isoformat(),
                payload.inspector_id,
            ),
        )
        if cursor.lastrowid is None:
            raise RuntimeError("SQLite did not return an inspection ID")
        inspection_id = cursor.lastrowid

    return {
        "inspection_id": inspection_id,
        "tyre_id": tyre_id,
        "passed": payload.passed,
        "defect_code": payload.defect_code,
        "inspected_at": inspected_at.isoformat(),
    }


@app.get("/tyres")
def list_tyres(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    user: dict[str, int | str] = Depends(require_user),
) -> dict[str, object]:
    with database() as connection:
        total = connection.execute("SELECT COUNT(*) AS count FROM tyre_tags").fetchone()["count"]
        rows = connection.execute(
            """SELECT t.tyre_id, t.epc, t.description,
                   (SELECT o.station_id FROM observations o WHERE o.epc = t.epc
                    ORDER BY julianday(o.timestamp) DESC, o.observation_id DESC LIMIT 1) AS current_station,
                   (SELECT o.timestamp FROM observations o WHERE o.epc = t.epc
                    ORDER BY julianday(o.timestamp) DESC, o.observation_id DESC LIMIT 1) AS latest_read_at,
                   (SELECT q.passed FROM quality_inspections q WHERE q.epc = t.epc
                    ORDER BY julianday(q.inspected_at) DESC, q.inspection_id DESC LIMIT 1) AS latest_passed,
                   (SELECT q.inspected_at FROM quality_inspections q WHERE q.epc = t.epc
                    ORDER BY julianday(q.inspected_at) DESC, q.inspection_id DESC LIMIT 1) AS latest_inspected_at
               FROM tyre_tags t ORDER BY t.tyre_id LIMIT ? OFFSET ?""",
            (limit, offset),
        ).fetchall()
    items = []
    for row in rows:
        item = dict(row)
        passed = item.pop("latest_passed")
        item["quality_status"] = "PENDING" if passed is None else ("PASS" if passed else "FAIL")
        items.append(item)
    return {"total": total, "limit": limit, "offset": offset, "items": items}


@app.get("/tyres/{tyre_id}")
def get_tyre(tyre_id: str, user: dict[str, int | str] = Depends(require_user)) -> dict[str, object]:
    with database() as connection:
        tag = connection.execute(
            "SELECT epc, tyre_id, description, registered_at FROM tyre_tags WHERE tyre_id = ?",
            (tyre_id,),
        ).fetchone()
        if tag is None:
            raise HTTPException(status_code=404, detail="Unknown tyre_id")

        observations = connection.execute(
            """SELECT observation_id, event_id, reader_id, antenna_id, station_id, rssi_dbm, timestamp
               FROM observations WHERE epc = ?
               ORDER BY julianday(timestamp), observation_id""",
            (tag["epc"],),
        ).fetchall()
        inspections = connection.execute(
            """SELECT inspection_id, passed, defect_code, notes, inspected_at, inspector_id
               FROM quality_inspections WHERE epc = ?
               ORDER BY julianday(inspected_at), inspection_id""",
            (tag["epc"],),
        ).fetchall()

    latest_observation = observations[-1] if observations else None
    latest_inspection = inspections[-1] if inspections else None
    return {
        "tyre": dict(tag),
        "current_station": latest_observation["station_id"] if latest_observation else None,
        "quality_status": (
            "PASS" if latest_inspection["passed"] else "FAIL"
        ) if latest_inspection else "PENDING",
        "latest_inspection": dict(latest_inspection) if latest_inspection else None,
        "observations": [dict(row) for row in observations],
        "inspections": [dict(row) for row in inspections],
    }


FRONTEND_DIR = PROJECT_ROOT / "frontend" / "dist"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
