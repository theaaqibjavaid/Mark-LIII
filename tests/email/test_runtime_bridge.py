import asyncio

from actions.email_common import run


def test_run_executes_coroutine_without_an_existing_event_loop():
    async def operation():
        await asyncio.sleep(0)
        return "ok"

    assert run(operation()) == "ok"


def test_run_executes_coroutine_from_an_active_event_loop():
    async def operation():
        await asyncio.sleep(0)
        return "ok"

    async def caller():
        return run(operation())

    assert asyncio.run(caller()) == "ok"
