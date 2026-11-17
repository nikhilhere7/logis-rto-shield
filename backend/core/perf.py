"""Request timing for production diagnosis.

One log line per measured request, on the "logis.perf" logger, for example:

    perf op=commit status=ok total_ms=8421.3 download_ms=310.2 parse_ms=95.4 validate_ms=402.8 ... batch_id=17

Only durations and safe identifiers (numeric ids, dataset type, row and byte counts) are ever logged:
never passwords, tokens, emails, names, file contents or exception messages (they can quote user data).
On an exception the line says status=error and the exception's class name, and the exception is re-raised
unchanged, so Django and DRF still handle and log it exactly as before.
"""
import logging
from contextlib import contextmanager
from time import perf_counter

logger = logging.getLogger("logis.perf")


def _ms(seconds):
    return f"{seconds * 1000:.1f}"


class RequestTimer:
    """Use as `with RequestTimer("signup") as t:` and time parts with `with t.step("validate"):`.
    A step entered more than once adds up. Extra safe fields can be set at any time with t.set(key=value)."""

    def __init__(self, op, **fields):
        self.op = op
        self.fields = dict(fields)
        self.steps = {}
        self._start = None

    def set(self, **fields):
        self.fields.update(fields)

    @contextmanager
    def step(self, name):
        start = perf_counter()
        try:
            yield
        finally:
            self.steps[name] = self.steps.get(name, 0.0) + (perf_counter() - start)

    def __enter__(self):
        self._start = perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            total = perf_counter() - self._start
            parts = [f"perf op={self.op}", f"status={'ok' if exc_type is None else 'error'}", f"total_ms={_ms(total)}"]
            parts += [f"{name}_ms={_ms(sec)}" for name, sec in self.steps.items()]
            parts += [f"{k}={v}" for k, v in self.fields.items() if v is not None]
            if exc_type is not None:
                parts.append(f"error={exc_type.__name__}")
            logger.info(" ".join(parts))
        except Exception:  # timing must never break a request
            pass
        return False  # never swallow the exception


@contextmanager
def maybe_step(timer, name):
    """timer.step(name) when a timer is given, otherwise nothing. Lets shared helpers be timed optionally."""
    if timer is None:
        yield
    else:
        with timer.step(name):
            yield
