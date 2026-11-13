"""Run a function with a time limit.

Drop-in replacement for the two names this project used from the
unmaintained ``func-timeout`` package (no release since 2019):
``func_timeout(timeout, func, args=(), kwargs=None)`` and
``FunctionTimedOut``. Standard library only.

The function runs in a daemon thread. When the limit passes, the caller gets
``FunctionTimedOut`` at once and the worker thread is asked to stop by raising
``FunctionTimedOut`` inside it (CPython's ``PyThreadState_SetAsyncExc``, the
same mechanism func-timeout used). A thread blocked inside native code stops
when it next returns to Python; being a daemon thread, it never keeps the
process alive.
"""

import ctypes
import threading

__all__ = ["FunctionTimedOut", "func_timeout"]


class FunctionTimedOut(Exception):
    """The function did not return within the time limit."""

    def __init__(self, msg="", timedOutAfter=None, timedOutFunction=None,
                 timedOutArgs=None, timedOutKwargs=None):
        self.timedOutAfter = timedOutAfter
        self.timedOutFunction = timedOutFunction
        self.timedOutArgs = timedOutArgs
        self.timedOutKwargs = timedOutKwargs
        if not msg:
            name = getattr(timedOutFunction, "__name__", "function")
            msg = f"{name} timed out after {timedOutAfter} seconds"
        super().__init__(msg)


def _stop_thread(thread):
    ident = thread.ident
    if ident is None or not thread.is_alive():
        return
    ctypes.pythonapi.PyThreadState_SetAsyncExc(
        ctypes.c_ulong(ident), ctypes.py_object(FunctionTimedOut)
    )


def func_timeout(timeout, func, args=(), kwargs=None):
    """Call ``func(*args, **kwargs)``; raise FunctionTimedOut after ``timeout`` seconds.

    Exceptions raised by ``func`` reach the caller unchanged.
    """
    kwargs = kwargs or {}
    outcome = {}

    def runner():
        try:
            outcome["value"] = func(*args, **kwargs)
        except FunctionTimedOut:
            pass
        except BaseException as exc:  # handed back to the caller below
            outcome["error"] = exc

    thread = threading.Thread(target=runner, name=f"func_timeout:{getattr(func, '__name__', 'fn')}", daemon=True)
    thread.start()
    thread.join(timeout)
    if thread.is_alive():
        _stop_thread(thread)
        raise FunctionTimedOut(timedOutAfter=timeout, timedOutFunction=func,
                               timedOutArgs=args, timedOutKwargs=kwargs)
    if "error" in outcome:
        raise outcome["error"]
    return outcome.get("value")
