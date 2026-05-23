"""Runtime context shared across command handlers.

A small dataclass that we pass to each ``make_handlers`` factory so command
modules don't reach into globals or telegram ``Application.bot_data``. Keeping
this explicit makes commands trivially unit-testable.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.audit import AuditLogger
from app.config import AppConfig
from app.confirmations import ConfirmationStore
from app.oci_client import OciClient


@dataclass(frozen=True)
class AppContext:
    config: AppConfig
    oci: OciClient
    audit: AuditLogger
    confirmations: ConfirmationStore
    version: str = "0.1.0"
