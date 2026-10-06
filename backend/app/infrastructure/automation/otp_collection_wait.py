# File: backend/app/infrastructure/automation/otp_collection_wait.py
import asyncio
from app.domain.ports.email_verification import VerificationError


async def collect_command(collector, broker, epoch, challenge_id):
    """Collector completion must not cancel the waiter consuming its accepted code."""
    reader = asyncio.create_task(collector.collect(epoch, challenge_id))
    waiter = asyncio.create_task(broker.wait(epoch.task_id, epoch.attempt_id, challenge_id))
    try:
        done, _ = await asyncio.wait((reader, waiter), return_when=asyncio.FIRST_COMPLETED)
        if waiter in done:
            command = waiter.result()
            if reader.done() and not reader.cancelled():
                error = reader.exception()
                if error is not None and not isinstance(error, VerificationError):
                    raise error
            return command
        reader.result()
        return await waiter
    finally:
        for child in (reader, waiter):
            if not child.done():
                child.cancel()
        await asyncio.gather(reader, waiter, return_exceptions=True)
