import functools
import itertools
import logging
import threading
import time
from collections import deque
from datetime import datetime, timezone


logger = logging.getLogger("youmood")


def retry(*delays, bypass=(), repeat_last=False):
    assert not (not delays and repeat_last)

    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            delays_ = itertools.chain(delays, itertools.repeat(delays[-1])) if repeat_last else delays
            for delay in delays_:
                try:
                    return fn(*args, **kwargs)
                except (NoRetry, *bypass):
                    raise
                except Exception as error:
                    logger.error("error: %s", error)
                    time.sleep(delay)
            return fn(*args, **kwargs)
        return wrapper
    return decorator


class Error(Exception):
    @classmethod
    def assert_(cls, true, message):
        if not true:
            raise cls(message)


class NoRetry(Error):
    pass


def rate_limit(*, bucket_time, bucket_size=1):
    bucket = deque()

    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            while len(bucket) >= bucket_size:
                elapsed = time.monotonic() - bucket[0]
                delay = bucket_time - elapsed
                if delay > 0:
                    time.sleep(delay)
                bucket.popleft()
            bucket.append(time.monotonic())
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def now():
    return datetime.utcnow().replace(tzinfo=timezone.utc)


def fromtimestamp(seconds):
    return datetime.utcfromtimestamp(seconds).replace(tzinfo=timezone.utc)


def cached(timeout):
    def decorator(fn):
        cache = {}

        def wrapper(*args, **kwargs):
            key = args + tuple(sorted(kwargs.items(), key=lambda pair: pair[0]))
            try:
                value, expired = cache[key]
                if expired < time.monotonic():
                    raise KeyError()
            except KeyError:
                value = fn(*args, **kwargs)
                cache[key] = (value, time.monotonic() + timeout)
            return value
        return wrapper
    return decorator


def start_thread(fn, *args, **kwargs):
    thread = threading.Thread(target=fn, args=args, kwargs=kwargs, daemon=True)
    thread.start()
    return thread
