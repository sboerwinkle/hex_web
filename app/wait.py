import time
import asyncio

async def until(when):
    now = time.monotonic()
    if (now > when):
        return now
    await asyncio.sleep(when-now)
    # Assume we came out close-enough to the desired time.
    # I feel like `return time.monotonic()` would be a bad idea, but I can't put my finger on why?
    return when
