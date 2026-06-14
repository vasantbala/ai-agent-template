from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config.settings import ScheduleConfig
from triggers.scheduler import start_scheduler


def make_app(system_prompt: str = "You are helpful.") -> MagicMock:
    mock_prompts = MagicMock()
    mock_prompts.get_system_prompt.return_value = system_prompt

    mock_graph = MagicMock()
    mock_graph.ainvoke = AsyncMock(return_value={
        "tenant_id": "t1", "session_id": "s1", "messages": [],
        "tasks": [], "current_task_index": 0, "iteration": 1,
        "tokens_used": 0, "cost_usd": 0.0, "error": None,
    })

    app = MagicMock()
    app.state.prompts = mock_prompts
    app.state.graph = mock_graph
    return app


class TestStartScheduler:
    def test_returns_none_when_disabled(self):
        config = ScheduleConfig(enabled=False)
        result = start_scheduler(make_app(), config)
        assert result is None

    async def test_returns_scheduler_when_enabled(self):
        config = ScheduleConfig(enabled=True)
        scheduler = start_scheduler(make_app(), config)
        try:
            assert isinstance(scheduler, AsyncIOScheduler)
        finally:
            if scheduler:
                scheduler.shutdown(wait=False)

    async def test_scheduler_starts_when_enabled(self):
        config = ScheduleConfig(enabled=True)
        scheduler = start_scheduler(make_app(), config)
        try:
            assert scheduler.running
        finally:
            if scheduler:
                scheduler.shutdown(wait=False)

    async def test_job_added_with_correct_cron(self):
        config = ScheduleConfig(enabled=True, cron="0 6 * * 1")
        scheduler = start_scheduler(make_app(), config)
        try:
            jobs = scheduler.get_jobs()
            assert len(jobs) == 1
            trigger = jobs[0].trigger
            assert "0" in str(trigger) or "6" in str(trigger)
        finally:
            if scheduler:
                scheduler.shutdown(wait=False)

    async def test_run_calls_run_agent_with_correct_args(self):
        config = ScheduleConfig(
            enabled=True,
            cron="0 9 * * *",
            input="Daily digest",
            tenant_id="acme",
            session_id_prefix="sched",
        )
        app = make_app("System prompt here.")
        scheduler = start_scheduler(app, config)
        try:
            jobs = scheduler.get_jobs()
            assert len(jobs) == 1
            _run = jobs[0].func

            with patch("agent.graph.run_agent", new_callable=AsyncMock) as mock_run:
                mock_run.return_value = MagicMock()
                await _run()
                mock_run.assert_awaited_once()
                call_kwargs = mock_run.call_args.kwargs
                assert call_kwargs["tenant_id"] == "acme"
                assert call_kwargs["user_input"] == "Daily digest"
                assert call_kwargs["session_id"].startswith("sched-")
                assert call_kwargs["system_prompt"] == "System prompt here."
        finally:
            if scheduler:
                scheduler.shutdown(wait=False)

    async def test_session_id_uses_prefix(self):
        config = ScheduleConfig(enabled=True, session_id_prefix="test-prefix")
        app = make_app()
        scheduler = start_scheduler(app, config)
        try:
            jobs = scheduler.get_jobs()
            _run = jobs[0].func

            captured_ids: list[str] = []

            async def fake_run(**kwargs):
                captured_ids.append(kwargs.get("session_id", ""))

            with patch("agent.graph.run_agent", new_callable=AsyncMock, side_effect=fake_run):
                await _run()

            assert captured_ids[0].startswith("test-prefix-")
        finally:
            if scheduler:
                scheduler.shutdown(wait=False)
