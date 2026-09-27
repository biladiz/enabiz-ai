"""SQLite database for persistent health record storage.

Uses aiosqlite for fully async database operations.
Supports deduplication, full-text search, and CSV export.
"""

from __future__ import annotations

import csv
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import aiosqlite

from enabiz_ai.extraction.models import LabReport, LabTest, Prescription, RadiologyReport

logger = logging.getLogger(__name__)

# ── Schema ─────────────────────────────────────────────────────────

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS lab_reports (
    report_id TEXT PRIMARY KEY,
    date TEXT NOT NULL,
    hospital TEXT,
    doctor TEXT,
    raw_text TEXT,
    source_file TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS lab_tests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id TEXT NOT NULL,
    test_name TEXT NOT NULL,
    value TEXT NOT NULL,
    unit TEXT,
    reference_range TEXT,
    is_abnormal INTEGER,
    notes TEXT,
    FOREIGN KEY (report_id) REFERENCES lab_reports(report_id)
);

CREATE TABLE IF NOT EXISTS prescriptions (
    prescription_id TEXT PRIMARY KEY,
    date TEXT NOT NULL,
    medication TEXT NOT NULL,
    dosage TEXT,
    frequency TEXT,
    quantity TEXT,
    prescriber TEXT,
    hospital TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS radiology_reports (
    report_id TEXT PRIMARY KEY,
    date TEXT NOT NULL,
    modality TEXT NOT NULL,
    body_part TEXT,
    findings TEXT NOT NULL,
    impression TEXT,
    hospital TEXT,
    doctor TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS vaccinations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vaccine_name TEXT NOT NULL,
    date TEXT NOT NULL,
    dose_number INTEGER,
    facility TEXT,
    batch_number TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS diagnoses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    diagnosis TEXT NOT NULL,
    clinic TEXT,
    doctor TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS visits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT,
    hospital TEXT,
    clinic TEXT,
    doctor TEXT,
    tracking_no TEXT,
    raw_details TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sync_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sync_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'completed',
    records_synced INTEGER DEFAULT 0,
    started_at TEXT NOT NULL,
    completed_at TEXT DEFAULT (datetime('now')),
    notes TEXT
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_lab_reports_date ON lab_reports(date);
CREATE INDEX IF NOT EXISTS idx_lab_tests_report ON lab_tests(report_id);
CREATE INDEX IF NOT EXISTS idx_prescriptions_date ON prescriptions(date);
CREATE INDEX IF NOT EXISTS idx_radiology_date ON radiology_reports(date);
CREATE INDEX IF NOT EXISTS idx_diagnoses_date ON diagnoses(date);
CREATE INDEX IF NOT EXISTS idx_visits_date ON visits(date);
CREATE INDEX IF NOT EXISTS idx_sync_log_type ON sync_log(sync_type);
"""


class HealthDatabase:
    """Async SQLite database for health record storage.

    Usage:
        async with HealthDatabase(Path("~/.enabiz-ai/health.db")) as db:
            await db.save_lab_report(report)
            reports = await db.get_lab_reports(since=datetime(2024, 1, 1))
    """

    def __init__(self, db_path: Path) -> None:
        """Initialize the database.

        Args:
            db_path: Path to the SQLite database file.
        """
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[aiosqlite.Connection] = None

    async def initialize(self) -> None:
        """Create the database connection and tables."""
        self._conn = await aiosqlite.connect(str(self.db_path))
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA foreign_keys = ON;")
        await self._conn.execute("PRAGMA journal_mode = WAL;")
        await self._conn.execute("PRAGMA busy_timeout = 5000;")
        await self._conn.executescript(SCHEMA_SQL)
        await self._conn.commit()
        logger.info("Database initialized at %s (WAL mode enabled)", self.db_path)

    async def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            await self._conn.close()
            self._conn = None

    async def __aenter__(self) -> HealthDatabase:
        await self.initialize()
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self.close()

    # ── Lab Reports ────────────────────────────────────────────────

    async def save_lab_report(self, report: LabReport) -> bool:
        """Save a lab report with its tests. Skips if report_id already exists.

        Args:
            report: The lab report to save.

        Returns:
            True if saved, False if already exists (dedup).
        """
        if self._conn is None:
            raise RuntimeError("Database not initialized. Use 'async with HealthDatabase(path) as db:' context manager.")

        # Check for duplicate
        cursor = await self._conn.execute(
            "SELECT 1 FROM lab_reports WHERE report_id = ?",
            (report.report_id,),
        )
        if await cursor.fetchone():
            logger.debug("Lab report %s already exists — skipping", report.report_id)
            return False

        await self._conn.execute(
            """INSERT INTO lab_reports (report_id, date, hospital, doctor, raw_text, source_file)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                report.report_id,
                report.date.isoformat(),
                report.hospital,
                report.doctor,
                report.raw_text,
                report.source_file,
            ),
        )

        for test in report.tests:
            await self._conn.execute(
                """INSERT INTO lab_tests (report_id, test_name, value, unit, reference_range, is_abnormal, notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    report.report_id,
                    test.test_name,
                    test.value,
                    test.unit,
                    test.reference_range,
                    1 if test.is_abnormal else (0 if test.is_abnormal is False else None),
                    test.notes,
                ),
            )

        await self._conn.commit()
        logger.info("Saved lab report %s with %d tests", report.report_id, len(report.tests))
        return True

    async def get_lab_reports(
        self,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
    ) -> list[LabReport]:
        """Retrieve lab reports, optionally filtered by date range.

        Args:
            since: Only include reports on or after this date.
            until: Only include reports on or before this date.

        Returns:
            List of LabReport objects with their tests.
        """
        if self._conn is None:
            raise RuntimeError("Database not initialized. Use 'async with HealthDatabase(path) as db:' context manager.")

        query = "SELECT * FROM lab_reports WHERE 1=1"
        params: list = []

        if since:
            query += " AND date >= ?"
            params.append(since.isoformat())
        if until:
            query += " AND date <= ?"
            params.append(until.isoformat())

        query += " ORDER BY date DESC"

        reports = []
        async with self._conn.execute(query, params) as cursor:
            async for row in cursor:
                report_id = row["report_id"]

                # Fetch associated tests
                tests = []
                async with self._conn.execute(
                    "SELECT * FROM lab_tests WHERE report_id = ?",
                    (report_id,),
                ) as test_cursor:
                    async for test_row in test_cursor:
                        is_abn = test_row["is_abnormal"]
                        tests.append(LabTest(
                            test_name=test_row["test_name"],
                            value=test_row["value"],
                            unit=test_row["unit"],
                            reference_range=test_row["reference_range"],
                            is_abnormal=True if is_abn == 1 else (False if is_abn == 0 else None),
                            notes=test_row["notes"],
                        ))

                reports.append(LabReport(
                    report_id=report_id,
                    date=datetime.fromisoformat(row["date"]),
                    hospital=row["hospital"],
                    doctor=row["doctor"],
                    tests=tests,
                    raw_text=row["raw_text"],
                    source_file=row["source_file"],
                ))

        return reports

    # ── Prescriptions ──────────────────────────────────────────────

    async def save_prescription(self, prescription: Prescription) -> bool:
        """Save a prescription. Skips if already exists.

        Returns:
            True if saved, False if duplicate.
        """
        if self._conn is None:
            raise RuntimeError("Database not initialized. Use 'async with HealthDatabase(path) as db:' context manager.")

        cursor = await self._conn.execute(
            "SELECT 1 FROM prescriptions WHERE prescription_id = ?",
            (prescription.prescription_id,),
        )
        if await cursor.fetchone():
            return False

        await self._conn.execute(
            """INSERT INTO prescriptions
               (prescription_id, date, medication, dosage, frequency, quantity, prescriber, hospital)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                prescription.prescription_id,
                prescription.date.isoformat(),
                prescription.medication,
                prescription.dosage,
                prescription.frequency,
                prescription.quantity,
                prescription.prescriber,
                prescription.hospital,
            ),
        )
        await self._conn.commit()
        return True

    async def get_prescriptions(
        self, since: Optional[datetime] = None
    ) -> list[Prescription]:
        """Retrieve prescriptions, optionally filtered by date."""
        if self._conn is None:
            raise RuntimeError("Database not initialized. Use 'async with HealthDatabase(path) as db:' context manager.")

        query = "SELECT * FROM prescriptions"
        params: list = []

        if since:
            query += " WHERE date >= ?"
            params.append(since.isoformat())

        query += " ORDER BY date DESC"

        prescriptions = []
        async with self._conn.execute(query, params) as cursor:
            async for row in cursor:
                prescriptions.append(Prescription(
                    prescription_id=row["prescription_id"],
                    date=datetime.fromisoformat(row["date"]),
                    medication=row["medication"],
                    dosage=row["dosage"],
                    frequency=row["frequency"],
                    quantity=row["quantity"],
                    prescriber=row["prescriber"],
                    hospital=row["hospital"],
                ))

        return prescriptions

    # ── Diagnoses ──────────────────────────────────────────────────

    async def save_diagnosis(self, date: str, diagnosis: str, clinic: str | None = None, doctor: str | None = None) -> bool:
        """Save a diagnosis record. Skips duplicate entries."""
        if self._conn is None:
            raise RuntimeError("Database not initialized. Use 'async with HealthDatabase(path) as db:' context manager.")
        cursor = await self._conn.execute(
            "SELECT 1 FROM diagnoses WHERE date = ? AND diagnosis = ?",
            (date, diagnosis),
        )
        if await cursor.fetchone():
            return False

        await self._conn.execute(
            """INSERT INTO diagnoses (date, diagnosis, clinic, doctor)
               VALUES (?, ?, ?, ?)""",
            (date, diagnosis, clinic, doctor),
        )
        await self._conn.commit()
        return True

    async def get_diagnoses(self) -> list[dict]:
        """Retrieve all diagnoses ordered by date descending."""
        if self._conn is None:
            raise RuntimeError("Database not initialized. Use 'async with HealthDatabase(path) as db:' context manager.")
        results = []
        async with self._conn.execute("SELECT * FROM diagnoses ORDER BY date DESC") as cursor:
            async for row in cursor:
                results.append(dict(row))
        return results

    # ── Doctor Visits ──────────────────────────────────────────────

    async def save_visit(self, date: str | None, hospital: str | None, clinic: str | None = None, doctor: str | None = None, tracking_no: str | None = None, raw_details: str | None = None) -> bool:
        """Save a doctor visit record."""
        if self._conn is None:
            raise RuntimeError("Database not initialized. Use 'async with HealthDatabase(path) as db:' context manager.")

        # Dedup: check by tracking_no if available, otherwise by composite key
        if tracking_no:
            cursor = await self._conn.execute("SELECT 1 FROM visits WHERE tracking_no = ?", (tracking_no,))
            if await cursor.fetchone():
                return False
        else:
            # BUG-2 fix: Composite dedup key for visits without tracking number
            detail_snippet = (raw_details or "")[:100]
            cursor = await self._conn.execute(
                "SELECT 1 FROM visits WHERE date = ? AND hospital = ? AND SUBSTR(COALESCE(raw_details, ''), 1, 100) = ?",
                (date, hospital, detail_snippet),
            )
            if await cursor.fetchone():
                return False

        await self._conn.execute(
            """INSERT INTO visits (date, hospital, clinic, doctor, tracking_no, raw_details)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (date, hospital, clinic, doctor, tracking_no, raw_details),
        )
        await self._conn.commit()
        return True

    async def get_visits(self) -> list[dict]:
        """Retrieve all doctor visits ordered by date descending."""
        if self._conn is None:
            raise RuntimeError("Database not initialized. Use 'async with HealthDatabase(path) as db:' context manager.")
        results = []
        async with self._conn.execute("SELECT * FROM visits ORDER BY date DESC") as cursor:
            async for row in cursor:
                results.append(dict(row))
        return results

    # ── Sync Log ───────────────────────────────────────────────────

    async def get_latest_sync(self, sync_type: str = "all") -> Optional[datetime]:
        """Get the timestamp of the last successful sync.

        Args:
            sync_type: Type of sync to check (e.g., 'labs', 'prescriptions', 'all').

        Returns:
            Datetime of last sync, or None if never synced.
        """
        if self._conn is None:
            raise RuntimeError("Database not initialized. Use 'async with HealthDatabase(path) as db:' context manager.")

        cursor = await self._conn.execute(
            """SELECT completed_at FROM sync_log
               WHERE sync_type = ? AND status = 'completed'
               ORDER BY completed_at DESC LIMIT 1""",
            (sync_type,),
        )
        row = await cursor.fetchone()
        if row and row["completed_at"]:
            return datetime.fromisoformat(row["completed_at"])
        return None

    async def record_sync(
        self,
        sync_type: str,
        records_synced: int = 0,
        status: str = "completed",
        notes: str | None = None,
    ) -> None:
        """Record a sync event in the log.

        Args:
            sync_type: Type of sync performed.
            records_synced: Number of records synced.
            status: Sync status ('completed', 'failed', 'partial').
            notes: Additional notes.
        """
        if self._conn is None:
            raise RuntimeError("Database not initialized. Use 'async with HealthDatabase(path) as db:' context manager.")

        await self._conn.execute(
            """INSERT INTO sync_log (sync_type, status, records_synced, started_at, notes)
               VALUES (?, ?, ?, datetime('now'), ?)""",
            (sync_type, status, records_synced, notes),
        )
        await self._conn.commit()

    # ── Search & Export ────────────────────────────────────────────

    async def search(self, query: str) -> list[dict]:
        """Search across all tables for matching records.

        Args:
            query: Search term.

        Returns:
            List of matching records as dicts with source table info.
        """
        if self._conn is None:
            raise RuntimeError("Database not initialized. Use 'async with HealthDatabase(path) as db:' context manager.")
        results = []
        search_term = f"%{query}%"

        # Search lab tests
        async with self._conn.execute(
            """SELECT lt.*, lr.date, lr.hospital FROM lab_tests lt
               JOIN lab_reports lr ON lt.report_id = lr.report_id
               WHERE lt.test_name LIKE ? OR lt.value LIKE ? OR lt.notes LIKE ?""",
            (search_term, search_term, search_term),
        ) as cursor:
            async for row in cursor:
                results.append({
                    "source": "lab_test",
                    "test_name": row["test_name"],
                    "value": row["value"],
                    "date": row["date"],
                    "hospital": row["hospital"],
                })

        # Search prescriptions
        async with self._conn.execute(
            """SELECT * FROM prescriptions
               WHERE medication LIKE ? OR prescriber LIKE ? OR hospital LIKE ?""",
            (search_term, search_term, search_term),
        ) as cursor:
            async for row in cursor:
                results.append({
                    "source": "prescription",
                    "medication": row["medication"],
                    "date": row["date"],
                    "prescriber": row["prescriber"],
                })

        return results

    async def export_csv(self, table: str, output_path: Path) -> int:
        """Export a table to CSV file.

        Args:
            table: Table name ('lab_reports', 'lab_tests', 'prescriptions', etc.)
            output_path: Path for the output CSV file.

        Returns:
            Number of rows exported.
        """
        if self._conn is None:
            raise RuntimeError("Database not initialized. Use 'async with HealthDatabase(path) as db:' context manager.")
        allowed_tables = {"lab_reports", "lab_tests", "prescriptions", "radiology_reports", "vaccinations", "diagnoses", "visits", "sync_log"}
        if table not in allowed_tables:
            raise ValueError(f"Invalid table: {table}. Allowed: {allowed_tables}")

        cursor = await self._conn.execute(f"SELECT * FROM {table}")  # noqa: S608
        rows = await cursor.fetchall()

        if not rows:
            logger.info("No data to export from %s", table)
            return 0

        output_path.parent.mkdir(parents=True, exist_ok=True)
        columns = [description[0] for description in cursor.description]

        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(columns)
            for row in rows:
                writer.writerow(list(row))

        logger.info("Exported %d rows from %s to %s", len(rows), table, output_path)
        return len(rows)

    async def get_stats(self) -> dict[str, int]:
        """Get database statistics.

        Returns:
            Dict with counts for each table.
        """
        if self._conn is None:
            raise RuntimeError("Database not initialized. Use 'async with HealthDatabase(path) as db:' context manager.")
        stats = {}
        allowed_tables = ("lab_reports", "lab_tests", "prescriptions", "radiology_reports", "vaccinations", "diagnoses", "visits")
        for table in allowed_tables:
            cursor = await self._conn.execute(f"SELECT COUNT(*) as cnt FROM {table}")  # noqa: S608
            row = await cursor.fetchone()
            stats[table] = row["cnt"] if row else 0

        return stats
