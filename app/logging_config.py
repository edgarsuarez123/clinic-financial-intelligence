import json
import logging
import sys
from datetime import datetime, timezone

class JsonFormatter(logging.Formatter):
    def format(self, record):
        # Deliberately omit arbitrary messages, request bodies, URLs and exceptions.
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "event": getattr(record, "event", "application_event"),
        }
        for key in ("request_id", "method", "route", "status", "duration_ms", "error_type"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        return json.dumps(payload)

def configure(level):
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("clinic.application")
    logger.handlers = [handler]
    logger.setLevel(level)
    logger.propagate = False
