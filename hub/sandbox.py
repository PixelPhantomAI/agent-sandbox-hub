"""
Sandbox Enforcement Layer
Provides rate limiting, content filtering, and audit logging for sandbox security.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import re
import threading


@dataclass
class AuditEntry:
    timestamp: datetime
    agent_name: str
    action: str
    details: dict


class SandboxEnforcer:
    # Rate limiting: 60 messages per minute
    RATE_LIMIT = 60
    RATE_WINDOW = 60  # seconds

    # URL pattern to block (external URLs)
    EXTERNAL_URL_PATTERN = re.compile(
        r'https?://(?!172\.28\.|localhost|127\.0\.0\.1)'
        r'(www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b'
        r'([-a-zA-Z0-9()@:%_\+.~#?&/=]*)',
        re.IGNORECASE
    )

    def __init__(self):
        self._rate_limits: dict[str, list[datetime]] = defaultdict(list)
        self._audit_log: list[AuditEntry] = []
        self._lock = threading.RLock()

    def check_rate_limit(self, agent_name: str) -> bool:
        """Check if agent is within rate limit. Returns True if allowed."""
        with self._lock:
            now = datetime.utcnow()
            window_start = now - timedelta(seconds=self.RATE_WINDOW)

            # Clean old entries
            self._rate_limits[agent_name] = [
                ts for ts in self._rate_limits[agent_name]
                if ts > window_start
            ]

            # Check limit
            if len(self._rate_limits[agent_name]) >= self.RATE_LIMIT:
                return False

            # Add current timestamp
            self._rate_limits[agent_name].append(now)
            return True

    def check_message_content(self, content: str) -> bool:
        """Check message content for external URLs. Returns True if clean."""
        if not content:
            return True
        # Block if external URLs are present
        return not bool(self.EXTERNAL_URL_PATTERN.search(content))

    def audit(self, agent_name: str, action: str, details: dict):
        """Record an audit entry."""
        with self._lock:
            entry = AuditEntry(
                timestamp=datetime.utcnow(),
                agent_name=agent_name,
                action=action,
                details=details
            )
            self._audit_log.append(entry)
            # Keep only last 10000 entries
            if len(self._audit_log) > 10000:
                self._audit_log = self._audit_log[-5000:]

    def get_audit_log(self, limit: int = 100) -> list[dict]:
        """Get recent audit log entries."""
        with self._lock:
            entries = self._audit_log[-limit:]
            return [{
                "timestamp": e.timestamp.isoformat(),
                "agent": e.agent_name,
                "action": e.action,
                "details": e.details
            } for e in entries]
