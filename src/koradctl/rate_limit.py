from __future__ import annotations

import time
from datetime import datetime


class RateLimit:
    """
    Limit how fast a loop is run.

    A common problem is wanting to run a loop at a certain rate. At each iteration, the
    loop should sleep long enough to maintain the target rate. This is the functionality
    provided by this class
    """

    def __init__(self, rate_hz: float) -> None:
        self._sleep_interval = 1.0 / rate_hz
        self._last_call: datetime | None = None

    def sleep(self) -> None:
        """
        Sleep to maintain the target rate.

        If the elapsed time is less than the desired loop time, sleep for the required
        amount of time. If it is greater, return immediately.
        """
        now = datetime.now()

        # The first time we call the function, we return immediately
        if self._last_call is None:
            self._last_call = now
            return

        # If the function has already been called, sleep to maintain the expected rate
        time_since_last = (now - self._last_call).total_seconds()
        sleep_duration = self._sleep_interval - time_since_last

        if sleep_duration > 0:
            time.sleep(sleep_duration)

        self._last_call = now
