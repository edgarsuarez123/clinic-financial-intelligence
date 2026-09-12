"""Durable background ingestion consumer. No dependency on the HTTP request lifecycle."""
import logging
import signal
from threading import Event
from ..settings import Settings
from ..logging_config import configure
from .repository import IngestionRepository
from ..appointments.repository import AppointmentRepository


def process_queues(repositories, logger):
    """Give each queue a turn, even if another queue fails or stays busy."""
    processed = failed = False
    for name, repository in repositories:
        try:
            processed = bool(repository.process_one()) or processed
        except Exception as exc:
            failed = True
            logger.error("", extra={"event": f"{name}.worker_error", "error_type": type(exc).__name__})
    return processed, failed


def main():
    settings=Settings.from_env()
    configure(settings.log_level)
    logger=logging.getLogger("clinic.application")
    repo=IngestionRepository(settings)
    repo.check_runtime()
    repositories=(("ingestion", repo), ("appointments", AppointmentRepository(settings)))
    stop=Event()
    for sig in (signal.SIGTERM,signal.SIGINT):
        signal.signal(sig,lambda *_:stop.set())
    while not stop.is_set():
        processed, failed = process_queues(repositories, logger)
        if failed: stop.wait(3)
        elif not processed: stop.wait(1)

if __name__ == "__main__": main()
