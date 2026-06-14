from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from config.settings import ScheduleConfig

if TYPE_CHECKING:
    from fastapi import FastAPI


def start_scheduler(app: FastAPI, schedule: ScheduleConfig) -> AsyncIOScheduler | None:
    if not schedule.enabled:
        return None

    scheduler = AsyncIOScheduler()

    async def _run() -> None:
        from agent.graph import run_agent

        session_id = f"{schedule.session_id_prefix}-{uuid.uuid4().hex[:8]}"
        system_prompt = app.state.prompts.get_system_prompt()
        await run_agent(
            graph=app.state.graph,
            tenant_id=schedule.tenant_id,
            session_id=session_id,
            user_input=schedule.input,
            system_prompt=system_prompt,
        )

    scheduler.add_job(_run, CronTrigger.from_crontab(schedule.cron))
    scheduler.start()
    return scheduler
