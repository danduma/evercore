"""Standalone evercore worker loop."""

from __future__ import annotations

import logging
import time

from evercore.db import create_db_and_tables, session_scope
from evercore.executors import ExecutorRegistry
from evercore.services import WorkerService
from evercore.settings import settings

logger = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    create_db_and_tables()

    service = WorkerService(ExecutorRegistry.default())
    logger.info("starting evercore worker: %s", settings.worker_id)

    while True:
        try:
            with session_scope() as session:
                result = service.process_once(session, worker_id=settings.worker_id)
            if not result.processed:
                time.sleep(settings.worker_poll_interval_seconds)
        except KeyboardInterrupt:
            logger.info("worker interrupted, exiting")
            break
        except Exception as exc:  # noqa: BLE001
            logger.exception("worker loop failure: %s", exc)
            time.sleep(settings.worker_poll_interval_seconds)


if __name__ == "__main__":
    main()
