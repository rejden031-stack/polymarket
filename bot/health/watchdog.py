import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


@dataclass
class HealthStatus:
    is_healthy: bool = True
    last_successful_scan: datetime | None = None
    last_error: str | None = None
    consecutive_errors: int = 0
    uptime_seconds: float = 0.0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "is_healthy": self.is_healthy,
            "last_successful_scan": self.last_successful_scan.isoformat() if self.last_successful_scan else None,
            "last_error": self.last_error,
            "consecutive_errors": self.consecutive_errors,
            "uptime_seconds": self.uptime_seconds,
        }


class Watchdog:
    def __init__(self, max_consecutive_errors: int = 5):
        self.status = HealthStatus()
        self._start_time = time.monotonic()
        self._max_errors = max_consecutive_errors

    def record_success(self):
        self.status.last_successful_scan = datetime.utcnow()
        self.status.consecutive_errors = 0
        self.status.last_error = None
        self.status.is_healthy = True
        self.status.uptime_seconds = time.monotonic() - self._start_time

    def record_error(self, error: str):
        self.status.consecutive_errors += 1
        self.status.last_error = error
        self.status.errors.append(error)
        if len(self.status.errors) > 100:
            self.status.errors.pop(0)

        if self.status.consecutive_errors >= self._max_errors:
            self.status.is_healthy = False
            logger.critical("Watchdog triggered: %d consecutive errors. Last: %s",
                            self.status.consecutive_errors, error)
