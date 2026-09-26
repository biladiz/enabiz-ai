"""Lab result PDF parser using IBM Docling.

Extracts structured table data from e-Nabız lab result PDFs using
Docling's TableFormer deep learning model for accurate table detection.
"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
try:
    import pandas as pd
except ImportError:
    pd = None  # type: ignore

from enabiz_ai.exceptions import DateParseError
from enabiz_ai.extraction.models import LabReport, LabTest, TURKISH_LAB_COLUMNS

logger = logging.getLogger(__name__)


class LabParser:
    """Parses lab result PDFs from e-Nabız using Docling.

    Uses IBM Docling's TableFormer model in ACCURATE mode to detect
    and extract complex borderless tables common in Turkish medical reports.

    Usage:
        parser = LabParser()
        report = parser.parse_pdf(Path("lab_results.pdf"))
    """

    def __init__(self) -> None:
        """Initialize the parser with Docling's document converter."""
        # Lazy import to avoid slow startup when not parsing
        self._converter = None

    def _get_converter(self):
        """Lazy-initialize the Docling converter."""
        if self._converter is None:
            from docling.document_converter import DocumentConverter, PdfFormatOption
            from docling.datamodel.base_models import InputFormat
            from docling.datamodel.pipeline_options import (
                PdfPipelineOptions,
                TableStructureOptions,
                TableFormerMode,
            )

            pipeline_options = PdfPipelineOptions()
            pipeline_options.do_table_structure = True
            pipeline_options.table_structure_options = TableStructureOptions(
                mode=TableFormerMode.ACCURATE,
                do_cell_matching=True,
            )

            self._converter = DocumentConverter(
                format_options={
                    InputFormat.PDF: PdfFormatOption(
                        pipeline_options=pipeline_options
                    )
                }
            )
            logger.info("Docling DocumentConverter initialized (ACCURATE mode)")

        return self._converter

    def parse_pdf(self, pdf_path: Path) -> LabReport:
        """Parse a lab result PDF file into a structured LabReport.

        Args:
            pdf_path: Path to the PDF file.

        Returns:
            A LabReport containing extracted test results.
        """
        logger.info("Parsing lab result PDF: %s", pdf_path.name)
        converter = self._get_converter()
        result = converter.convert(str(pdf_path))
        doc = result.document

        # Extract markdown for raw text storage
        raw_text = doc.export_to_markdown()

        # Extract tables
        tests: list[LabTest] = []
        for idx, table in enumerate(doc.tables):
            try:
                df = table.export_to_dataframe()
                logger.debug("Table %d: %d rows x %d cols", idx, len(df), len(df.columns))
                table_tests = self._parse_table(df)
                tests.extend(table_tests)
            except Exception as e:
                logger.warning("Failed to parse table %d: %s", idx, e)

        # Generate report ID from filename + hash
        report_id = self._generate_report_id(pdf_path)

        # Try to extract date from filename or text
        report_date = self._extract_date(pdf_path.stem, raw_text)

        report = LabReport(
            report_id=report_id,
            date=report_date,
            tests=tests,
            raw_text=raw_text[:5000] if raw_text else None,  # Truncate for storage
            source_file=str(pdf_path),
        )

        logger.info(
            "Parsed %d tests from %s (date: %s)",
            len(tests), pdf_path.name, report_date.isoformat(),
        )
        return report

    def parse_text(self, text: str, report_id: str = "manual") -> LabReport:
        """Parse lab results from raw text/markdown content.

        Args:
            text: Markdown or plain text containing lab results.
            report_id: Identifier for this report.

        Returns:
            A LabReport with extracted test data.
        """
        # Try to find table-like structures in text
        tests = self._parse_text_table(text)
        report_date = self._extract_date("", text)

        return LabReport(
            report_id=report_id,
            date=report_date,
            tests=tests,
            raw_text=text[:5000],
        )

    def _parse_table(self, df: Any) -> list[LabTest]:
        """Parse a pandas DataFrame (from Docling table) into LabTest objects.

        Maps Turkish column names to English fields using TURKISH_LAB_COLUMNS.

        Args:
            df: DataFrame from Docling table extraction.

        Returns:
            List of LabTest objects.
        """
        if df.empty:
            return []

        # Normalize column names
        column_mapping = {}
        for col in df.columns:
            col_lower = str(col).strip().lower()
            if col_lower in TURKISH_LAB_COLUMNS:
                column_mapping[col] = TURKISH_LAB_COLUMNS[col_lower]
            else:
                # Try partial matching
                for tr_name, en_name in TURKISH_LAB_COLUMNS.items():
                    if tr_name in col_lower or col_lower in tr_name:
                        column_mapping[col] = en_name
                        break

        if not column_mapping:
            logger.warning("Could not map any columns. Raw columns: %s", list(df.columns))
            # Attempt positional mapping if we have exactly the right number of columns
            if len(df.columns) >= 2:
                column_mapping = {
                    df.columns[0]: "test_name",
                    df.columns[1]: "value",
                }
                if len(df.columns) >= 3:
                    column_mapping[df.columns[2]] = "unit"
                if len(df.columns) >= 4:
                    column_mapping[df.columns[3]] = "reference_range"

        df_mapped = df.rename(columns=column_mapping)

        tests = []
        for _, row in df_mapped.iterrows():
            test_name = str(row.get("test_name", "")).strip()
            value = str(row.get("value", "")).strip()

            # Skip empty or header rows
            if not test_name or not value or test_name.lower() in ("tetkik adı", "test adı", "parametre"):
                continue

            unit = str(row.get("unit", "")).strip() or None
            ref_range = str(row.get("reference_range", "")).strip() or None
            notes = str(row.get("notes", "")).strip() or None

            # Determine if abnormal
            is_abnormal = self._check_abnormal(value, ref_range, notes)

            tests.append(LabTest(
                test_name=test_name,
                value=value,
                unit=unit,
                reference_range=ref_range,
                is_abnormal=is_abnormal,
                notes=notes,
            ))

        return tests

    def _parse_text_table(self, text: str) -> list[LabTest]:
        """Parse lab tests from markdown table text.

        Args:
            text: Text potentially containing markdown tables.

        Returns:
            List of LabTest objects found.
        """
        tests = []
        lines = text.strip().split("\n")

        for line in lines:
            if "|" not in line or line.strip().startswith("|-"):
                continue

            parts = [p.strip() for p in line.split("|") if p.strip()]
            if len(parts) >= 2:
                test_name = parts[0]
                value = parts[1]

                # Skip header rows
                if test_name.lower() in ("tetkik adı", "test adı", "test name", "parametre"):
                    continue

                unit = parts[2] if len(parts) > 2 else None
                ref_range = parts[3] if len(parts) > 3 else None
                notes = parts[4] if len(parts) > 4 else None

                is_abnormal = self._check_abnormal(value, ref_range, notes)

                tests.append(LabTest(
                    test_name=test_name,
                    value=value,
                    unit=unit,
                    reference_range=ref_range,
                    is_abnormal=is_abnormal,
                    notes=notes,
                ))

        return tests

    @staticmethod
    def _check_abnormal(
        value: str,
        reference_range: Optional[str],
        notes: Optional[str] = None,
    ) -> Optional[bool]:
        """Determine if a lab value is abnormal.

        Checks:
        1. Turkish flag markers (Y=Yüksek/High, D=Düşük/Low)
        2. Numeric comparison against reference range (both interval and < / > thresholds)

        Args:
            value: The test result value.
            reference_range: The normal reference range (e.g., "12.0-16.0", "< 1.0", "> 30").
            notes: Additional flags or notes.

        Returns:
            True if abnormal, False if normal, None if undetermined.
        """
        # Check flags in notes
        if notes:
            notes_upper = notes.upper().strip()
            if notes_upper in ("Y", "YÜKSEK", "YUKSEK", "H", "HIGH", "HH"):
                return True
            if notes_upper in ("D", "DÜŞÜK", "DUSUK", "L", "LOW", "LL"):
                return True
            if notes_upper in ("N", "NORMAL", ""):
                return False

        # Try numeric comparison
        if reference_range:
            try:
                numeric_value = float(re.sub(r"[^\d.]", "", value))
                ref_clean = reference_range.strip()

                # Parse "< 1.0"
                match_lt = re.match(r"<\s*([\d.]+)", ref_clean)
                if match_lt:
                    high = float(match_lt.group(1))
                    return numeric_value >= high

                # Parse "> 30"
                match_gt = re.match(r">\s*([\d.]+)", ref_clean)
                if match_gt:
                    low = float(match_gt.group(1))
                    return numeric_value <= low

                # Parse range like "12.0-16.0" or "12.0 - 16.0"
                match = re.match(r"([\d.]+)\s*[-–]\s*([\d.]+)", ref_clean)
                if match:
                    low = float(match.group(1))
                    high = float(match.group(2))
                    return numeric_value < low or numeric_value > high
            except (ValueError, AttributeError):
                pass

        return None

    @staticmethod
    def _generate_report_id(pdf_path: Path) -> str:
        """Generate a deterministic report ID from the file path using SHA-256."""
        content_hash = hashlib.sha256(str(pdf_path).encode("utf-8")).hexdigest()[:12]
        return f"lab_{pdf_path.stem}_{content_hash}"

    @staticmethod
    def _extract_date(filename: str, text: str, default: datetime | None = None) -> datetime:
        """Try to extract a date from the filename or text content.

        Looks for common date patterns:
        - YYYY-MM-DD, DD.MM.YYYY, DD/MM/YYYY

        Args:
            filename: The PDF filename (without extension).
            text: Raw text content.
            default: Optional fallback datetime if not found.

        Returns:
            Extracted datetime, or default if provided.

        Raises:
            DateParseError: If no date could be extracted and no default is provided.
        """
        # Common date patterns
        patterns = [
            (r"(\d{4})-(\d{2})-(\d{2})", "%Y-%m-%d"),
            (r"(\d{2})\.(\d{2})\.(\d{4})", "%d.%m.%Y"),
            (r"(\d{2})/(\d{2})/(\d{4})", "%d/%m/%Y"),
        ]

        search_text = f"{filename} {text[:1000]}"

        for pattern, fmt in patterns:
            match = re.search(pattern, search_text)
            if match:
                try:
                    date_str = match.group(0)
                    return datetime.strptime(date_str, fmt)
                except ValueError:
                    continue

        if default is not None:
            logger.warning("Could not extract date from filename/text, using default: %s", default)
            return default

        raise DateParseError(f"Could not extract date from filename '{filename}' or text content")
