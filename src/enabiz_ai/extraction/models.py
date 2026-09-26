"""Pydantic v2 data models for extracted health records.

All models support JSON serialization and database storage.
Turkish field name mappings are included for e-Nabız parsing.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, model_validator


class LabTest(BaseModel):
    """A single laboratory test result."""

    test_name: str = Field(description="Name of the test (e.g., Hemoglobin, Glucose)")
    value: str = Field(description="Test result value as string (may include non-numeric)")
    unit: Optional[str] = Field(default=None, description="Unit of measurement (e.g., g/dL, mg/dL)")
    reference_range: Optional[str] = Field(default=None, description="Normal reference range (e.g., '12.0-16.0')")
    is_abnormal: Optional[bool] = Field(default=None, description="Whether the value is outside reference range")
    notes: Optional[str] = Field(default=None, description="Additional notes or flags (Y=Yüksek, D=Düşük)")

    model_config = {"from_attributes": True}


class LabReport(BaseModel):
    """A complete laboratory report containing multiple test results."""

    report_id: str = Field(description="Unique report identifier")
    date: datetime = Field(description="Date of the lab report")
    hospital: Optional[str] = Field(default=None, description="Hospital or lab name")
    doctor: Optional[str] = Field(default=None, description="Ordering physician")
    tests: list[LabTest] = Field(default_factory=list, description="Individual test results")
    raw_text: Optional[str] = Field(default=None, description="Raw extracted text")
    source_file: Optional[str] = Field(default=None, description="Path to source PDF/file")

    model_config = {"from_attributes": True}


class Prescription(BaseModel):
    """A prescription record from e-Nabız."""

    prescription_id: str = Field(description="Unique prescription identifier")
    date: datetime = Field(description="Prescription date")
    medication: str = Field(description="Medication name")
    dosage: Optional[str] = Field(default=None, description="Dosage (e.g., '500mg')")
    frequency: Optional[str] = Field(default=None, description="Frequency (e.g., '2x1')")
    quantity: Optional[str] = Field(default=None, description="Quantity prescribed")
    prescriber: Optional[str] = Field(default=None, description="Prescribing physician")
    hospital: Optional[str] = Field(default=None, description="Hospital name")

    model_config = {"from_attributes": True}


class RadiologyReport(BaseModel):
    """A radiology/imaging report."""

    report_id: str = Field(description="Unique report identifier")
    date: datetime = Field(description="Report date")
    modality: str = Field(description="Imaging modality (X-ray, MRI, CT, USG)")
    body_part: Optional[str] = Field(default=None, description="Body part examined")
    findings: str = Field(description="Radiologist's findings")
    impression: Optional[str] = Field(default=None, description="Clinical impression/conclusion")
    hospital: Optional[str] = Field(default=None, description="Hospital name")
    doctor: Optional[str] = Field(default=None, description="Reporting radiologist")

    model_config = {"from_attributes": True}


class VaccinationRecord(BaseModel):
    """A vaccination record."""

    vaccine_name: str = Field(description="Vaccine name")
    date: datetime = Field(description="Vaccination date")
    dose_number: Optional[int] = Field(default=None, description="Dose number (1st, 2nd, booster)")
    facility: Optional[str] = Field(default=None, description="Vaccination facility")
    batch_number: Optional[str] = Field(default=None, description="Vaccine batch/lot number")

    model_config = {"from_attributes": True}


class HealthSummary(BaseModel):
    """Aggregated health data summary."""

    lab_reports: list[LabReport] = Field(default_factory=list)
    prescriptions: list[Prescription] = Field(default_factory=list)
    radiology: list[RadiologyReport] = Field(default_factory=list)
    vaccinations: list[VaccinationRecord] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=datetime.now)
    summary_text: Optional[str] = Field(default=None, description="LLM-generated health summary")

    model_config = {"from_attributes": True}

    @property
    def total_records(self) -> int:
        """Total number of health records across all categories."""
        return (
            len(self.lab_reports)
            + len(self.prescriptions)
            + len(self.radiology)
            + len(self.vaccinations)
        )


# ── Turkish → English column name mappings for lab result parsing ──

TURKISH_LAB_COLUMNS: dict[str, str] = {
    # Test name columns
    "tetkik adı": "test_name",
    "tetkik adi": "test_name",
    "test adı": "test_name",
    "test adi": "test_name",
    "parametre": "test_name",
    "analiz": "test_name",
    # Value columns
    "sonuç": "value",
    "sonuc": "value",
    "değer": "value",
    "deger": "value",
    "result": "value",
    # Unit columns
    "birim": "unit",
    "birimi": "unit",
    "unit": "unit",
    # Reference range columns
    "referans aralığı": "reference_range",
    "referans araligi": "reference_range",
    "referans": "reference_range",
    "ref. aralığı": "reference_range",
    "ref. araligi": "reference_range",
    "normal değer": "reference_range",
    "normal deger": "reference_range",
    # Status/flag columns
    "durum": "notes",
    "flag": "notes",
    "bayrak": "notes",
}
