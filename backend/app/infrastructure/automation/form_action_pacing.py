# File: backend/app/infrastructure/automation/form_action_pacing.py
from asyncio import sleep as _default_sleep
from collections.abc import Awaitable, Callable
from math import isfinite
from random import uniform as _default_uniform

DelaySampler = Callable[[float, float], float]
Sleeper = Callable[[float], Awaitable[None]]
MIN_ACTION_DELAY_SECONDS = 0.75
MAX_ACTION_DELAY_SECONDS = 3.0


class FormActionPacer:
    """Own the pauses between logical actions within one form preparation."""

    def __init__(self, *, delay_sampler: DelaySampler | None = None,
                 sleeper: Sleeper | None = None) -> None:
        self._delay_sampler = _default_uniform if delay_sampler is None else delay_sampler
        self._sleeper = _default_sleep if sleeper is None else sleeper
        self._has_previous_action = False

    async def before_action(self) -> None:
        if not self._has_previous_action:
            self._has_previous_action = True
            return
        seconds = self._delay_sampler(MIN_ACTION_DELAY_SECONDS, MAX_ACTION_DELAY_SECONDS)
        if (isinstance(seconds, bool) or not isinstance(seconds, (int, float))
                or not MIN_ACTION_DELAY_SECONDS <= seconds <= MAX_ACTION_DELAY_SECONDS
                or not isfinite(seconds)):
            raise ValueError("Invalid form action delay.")
        await self._sleeper(seconds)
