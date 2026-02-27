"""Standalone evercore worker loop."""

from __future__ import annotations

import logging
import time

from evercore.db import create_db_and_tables, session_scope
from evercore.executors import ExecutorRegistry
from evercore.services import SchedulerService, TicketService, WorkerService
from evercore.settings import settings
from evercore.workflow import WorkflowLoader

logger = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    create_db_and_tables()

    ticket_service = TicketService(WorkflowLoader(settings.workflow_dir_path))
    scheduler_service = SchedulerService(ticket_service)
    service = WorkerService(ExecutorRegistry.default())
    logger.info("starting evercore worker: %s", settings.worker_id)

    while True:
        try:
            with session_scope() as session:
                scheduled_count = scheduler_service.process_due_schedules(
                    session,
                    limit=settings.schedule_batch_size,
                )
                result = service.process_once(session, worker_id=settings.worker_id)
            if not result.processed and scheduled_count == 0:
                time.sleep(settings.worker_poll_interval_seconds)
        except KeyboardInterrupt:
            logger.info("worker interrupted, exiting")
            break
        except Exception as exc:  # noqa: BLE001
            logger.exception("worker loop failure: %s", exc)
            time.sleep(settings.worker_poll_interval_seconds)


if __name__ == "__main__":
    main()
