"""Appointment activity aggregates.

The package deliberately deals in appointment *volume* only.  It does not
accept or retain identifiers for people and it never writes to the financial
transaction tables.
"""

from .aggregation import AppointmentFact, aggregate_report
from .config import AppointmentConfig, DEFAULT_CATEGORY_LABELS
from .repository import AppointmentRepository

__all__ = [
    "AppointmentConfig",
    "AppointmentFact",
    "AppointmentRepository",
    "DEFAULT_CATEGORY_LABELS",
    "aggregate_report",
]
