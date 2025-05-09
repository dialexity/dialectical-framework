import asyncio
import inspect


def is_async(func=None):
    try:
        asyncio.get_running_loop()  # Check if an active event loop exists
        if func:
            # OPTIONAL: Check if the given function is async
            return inspect.iscoroutinefunction(func)
        return True
    except RuntimeError:
        return False
