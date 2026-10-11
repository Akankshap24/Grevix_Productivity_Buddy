import math
import sys
import threading
import time
from datetime import datetime, timezone


def _elapsed_clock():
    """Return a clock that keeps counting while the computer sleeps.

    time.monotonic() pauses during suspend on Linux and macOS, so comparing it
    with wall-clock time would report a "clock jump" every time a laptop wakes.
    """
    if hasattr(time, 'CLOCK_BOOTTIME'):  # Linux: includes suspend
        return lambda: time.clock_gettime(time.CLOCK_BOOTTIME)
    if sys.platform == 'darwin' and hasattr(time, 'CLOCK_MONOTONIC'):
        # On macOS, CLOCK_MONOTONIC keeps running during sleep.
        return lambda: time.clock_gettime(time.CLOCK_MONOTONIC)
    return time.monotonic  # Windows: already includes sleep


class DeadlineGuard:
    """Monitor clock stability and support safe clock-jump simulations.

    A detected jump stays flagged until someone acknowledges it with reset(),
    so every view (page render, API, rescue plan) agrees on the clock state.
    """

    MAX_SIMULATION_SECONDS = 86400

    def __init__(self, tolerance_seconds=5, clock=None):
        self.tolerance_seconds = tolerance_seconds
        self._elapsed = clock or _elapsed_clock()
        self._lock = threading.Lock()
        self.last_wall_time = time.time()
        self.last_elapsed_time = self._elapsed()
        self.simulated_skew_seconds = 0.0
        self.detected_jump_seconds = None
        self.detected_at_utc = None

    def _within_tolerance(self, seconds):
        return abs(seconds) <= self.tolerance_seconds

    def _status(self, observed_skew):
        if self.detected_jump_seconds is not None:
            message = 'Possible system clock jump detected. Deadline timing is uncertain.'
        elif not self._within_tolerance(self.simulated_skew_seconds):
            message = 'Simulated clock drift detected. Deadline timing is uncertain.'
        else:
            message = 'No significant clock jump detected.'

        return {
            'checked_at_utc': datetime.now(timezone.utc).isoformat(),
            'clock_skew_seconds': round(observed_skew, 2),
            'detected_jump_seconds': (
                None if self.detected_jump_seconds is None
                else round(self.detected_jump_seconds, 2)
            ),
            'detected_at_utc': self.detected_at_utc,
            'simulated_skew_seconds': self.simulated_skew_seconds,
            'tolerance_seconds': self.tolerance_seconds,
            'clock_suspicious': (
                self.detected_jump_seconds is not None
                or not self._within_tolerance(self.simulated_skew_seconds)
            ),
            'message': message,
        }

    def check_clock(self):
        with self._lock:
            wall_now = time.time()
            elapsed_now = self._elapsed()

            observed_skew = (wall_now - self.last_wall_time) - (elapsed_now - self.last_elapsed_time)

            self.last_wall_time = wall_now
            self.last_elapsed_time = elapsed_now

            if not self._within_tolerance(observed_skew):
                # Remember the largest jump until it is acknowledged.
                if self.detected_jump_seconds is None or abs(observed_skew) > abs(self.detected_jump_seconds):
                    self.detected_jump_seconds = observed_skew
                    self.detected_at_utc = datetime.now(timezone.utc).isoformat()

            return self._status(observed_skew)

    def reset(self):
        """Clear a detected jump and any simulation after the user has checked their clock."""
        with self._lock:
            self.simulated_skew_seconds = 0.0
            self.detected_jump_seconds = None
            self.detected_at_utc = None
            self.last_wall_time = time.time()
            self.last_elapsed_time = self._elapsed()
            return self._status(0.0)

    def simulate_clock_jump(self, jump_seconds):
        """Set simulated drift without changing the computer's actual clock."""
        if isinstance(jump_seconds, bool) or not isinstance(jump_seconds, (int, float)):
            raise ValueError('jump_seconds must be a number')

        if not math.isfinite(jump_seconds):
            raise ValueError('jump_seconds must be a finite number')

        if abs(jump_seconds) > self.MAX_SIMULATION_SECONDS:
            raise ValueError('Simulation jump cannot exceed 24 hours')

        with self._lock:
            self.simulated_skew_seconds = float(jump_seconds)
            suspicious = not self._within_tolerance(self.simulated_skew_seconds)
            return {
                'simulated_jump_seconds': self.simulated_skew_seconds,
                'simulated_jump_minutes': round(self.simulated_skew_seconds / 60, 2),
                'clock_suspicious': suspicious or self.detected_jump_seconds is not None,
                'message': (
                    'Simulated clock jump detected. Deadline timing is uncertain.'
                    if suspicious
                    else 'Simulation is within the clock tolerance.'
                ),
            }
