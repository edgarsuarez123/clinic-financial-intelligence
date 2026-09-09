"""Durable background ingestion consumer. No dependency on the HTTP request lifecycle."""
import logging
import signal
from threading import Event
from ..settings import Settings
from ..logging_config import configure
from .repository import IngestionRepository


def main():
    settings=Settings.from_env()
    configure(settings.log_level)
    logger=logging.getLogger("clinic.application")
    repo=IngestionRepository(settings)
    repo.check_runtime()
    stop=Event()
    for sig in (signal.SIGTERM,signal.SIGINT):
        signal.signal(sig,lambda *_:stop.set())
    while not stop.is_set():
        try:
            if not repo.process_one(): stop.wait(1)
        except Exception as exc:
            logger.error("",extra={"event":"ingestion.worker_error","error_type":type(exc).__name__})
            stop.wait(3)

if __name__ == "__main__": main()
