import asyncio
import traceback
from time import monotonic
from math import inf

from . import wait

NO_PATIENCE=1
THINK_PATIENCE=1
ACT_PATIENCE=2
SLOW_PATIENCE=3
MAX_PATIENCE=4

def bisect(l, p):
    min = 0
    max = len(l)
    while min != max:
        t = (min+max) // 2
        if p(l[t]):
            min = t+1
        else:
            max = t
    return min

class TaskQueue:
    def __init__(self):
        self.pending=[]
        self.immediates=[[]]
        self.running = 0
    def next_time(self):
        if len(self.pending):
            return self.pending[0].time
        return inf
    def wait_time(self, time):
        if time > self.next_time():
            raise Exception("Having a bad time")
        for t in self.pending:
            t.time -= time
    def schedule(self, func, delay, patience):
        task = Task(func, delay, patience)
        if delay < 0:
            raise Exception("Delay cannot be negative!")
        if delay == 0:
            self._immediately(task)
        else:
            ix = bisect(self.pending, lambda x: x.time <= delay)
            self.pending.insert(ix, task)
    def _immediately(self, task):
        "add the task to the (patience)th immediate list."
        "If there aren't that many immediate lists yet, pad with empty lists."
        if task.patience < self.running:
            while len(self.immediates) <= task.patience:
                self.immediates.append([])
            self.immediates[task.patience].append(task)
        else:
            self.pending.insert(0, task)
    def run(self, patience = MAX_PATIENCE+1):
        if self.next_time() < 0:
            raise Exception("Negative time on a task!")
        self.running = patience
        i = 0
        others = []
        for t in self.pending:
            if t.time == 0:
                if t.patience < self.running:
                    self._immediately(t)
                else:
                    others.append(t)
                i += 1
            else:
                break
        others += self.pending[i:]
        self.pending = others
        while True:
            for i in range(0, len(self.immediates)):
                if self.immediates[i]:
                    tmp = self.immediates[i]
                    self.immediates[i] = []
                    self.immediates[0] = tmp
                    break
            else:
                break # The dreaded python for/else construct
            to_run = self.immediates[0]
            while to_run:
                t = to_run.pop(0)
                try:
                    t.func()
                except Exception:
                    print("Exception running task:")
                    traceback.print_exc()
        self.running = 0

class MillisTaskQueue(TaskQueue):
    "TaskQueue that manages its own running by tying the tasks' time to real-world milliseconds"
    def __init__(self, callback, sec_per_turn=0.001):
        self.callback = callback
        self.sec_per_turn = sec_per_turn
        # Dummy task which immediately returns, just so we don't have to do `None` checks
        self.async_task = asyncio.create_task(asyncio.sleep(0))
        # Get current time as "0"
        self.zero_time = monotonic()
        super().__init__()
    async def loop(self):
        try:
            while True:
                next_time = self.next_time()
                if (next_time == inf):
                    return

                self.zero_time = await wait.until(self.zero_time + next_time*self.sec_per_turn)
                self.wait_time(next_time)

                self.run()
                self.callback()
        except Exception:
            print("Exception is MillisTaskQueue.loop:")
            traceback.print_exc()
    def schedule(self, func, delay, patience):
        if self.running != 0:
            # If we're in the middle of a task loop, schedule everything like normal, nothing need change
            super().schedule(func, delay, patience)
            return
        # Otherwise, something external is scheduling a task; we need to do some magic with the current time.
        delay += int((monotonic() - self.zero_time) / self.sec_per_turn)
        next_time = self.next_time()
        super().schedule(func, delay, patience)
        if delay < next_time:
            self.async_task.cancel()
            self.async_task = asyncio.create_task(self.loop())
    async def cancel(self):
        self.async_task.cancel()

class Task:
    def __init__(self, func, time=0, patience=0):
        self.func = func
        self.time = time
        self.patience = patience
