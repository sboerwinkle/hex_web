# I'm aiming to build out a modular system for defining actions and behaviors.
# Broadly, there are:
# - Actions which are taken "immediately". These are pretty much just functions, they know they're going to run.
# - Actions which are scheduled. These are going to be the behavior, plus a modular guard to see if they should run.
#   (of course, something to do "on failure" could also be worked in if that turns out to be a commonality)
# - Actions which trigger when something happens. These will *often* be also either delayed or require a claim (more on that later),
#   but they don't necessarily have to be. These modules deal with what shape is watched, watch cancellation, etc.
# - Actions which require a claim. Claims are the backbone of synchronized, fair interoperation across the board.
#   A claim's presence should be invisible to all but other claims,
#   and other claims are scrupulous about patience and not leaking information,
#   so really claims can spawn and do their checking during regular, non-affecting rounds.
#   If so, however, we just need to make extra sure that regular board interrogation isn't confused by claims.
#   If a claim succeeds it is obligated to "consume" the space next affecting round.
#     (Since the failed claims are probably going to be looking again right after)
#   Claims deal with what they conflict on (which is checked to be mutually agreeable),
#   who is better (on which they must also agree),
#   and they have a successful behavior (which they always schedule for AFFECT),
#   and a failed behavior (which will probably be an AFFECT action, like increasing their frustration)
#     (frustration is used in claim resolution, which is cross-entity reading, hence modifications are affecting)

class ResolutionGuard:
    pass
    """
    TODO: This might be handy; basically htere are probably going to be a lot of affecting functions that take multiple
    "things seen" and combine and publish them (like the Claimer's frustration resolution). Hence, this keeps a set of
    callables (which will be different per instance and method), and makes sure they're scheduled once.
    Or better yet, instantiate once per Resolution-Type method, and then invoke it when you want to make sure it's scheduled!
    (no sets that way)
    """

class SingleGuard(ent, sched_lambda):
    """
    A callable which wraps the provided scheduling lambda.
    Tasks scheduled this way ensure that only one is scheduled at a time
    (by preventing "overriden" tasks from running when they come time),
    and additionally make sure the ent is live before running them.
    """
    def __init__(self, ent, sched_lambda):
        self.ent = ent
        self.l = sched_lambda
        self.active = wrapper(None, None) # This one's never actually called, so the `None`s are fine.

    class wrapper:
        def __init__(self, ent, f):
            self.ent = ent
            self.f = f
            self.active = True
        def run(self):
            if self.active and self.ent.game is not None:
                self.f()

    def __call__(self, f, *a):
        self.active.active = False
        self.active = wrapper(self.ent, f)
        self.l(self.active.run, *a)

class Claimer:
    # Oh god so much TODO
    class Claim:
        def __init__(self, parent, something_else):
            self.parent = parent
            self.something_else = something_else
        def success(self):
            self.parent.sched(self.something_else.func, AFFECT)
            self.parent.success()
        def failure(self):
            self.parent.failure()
    def __init__(self, sched):
        self.frustration = 0
        self.sched = sched
        self._wins = 0
        self._losses = 0
        self._scheduled = False
    def sched_cleanup(self):
        if not self._scheduled:
            self._scheduled = True
            self.sched(self.cleanup_affect, AFFECT)
    def success(self):
        self._wins += 1
        self.sched_cleanup()
    def failure(self):
        self._losses += 1
        self.sched_cleanup()
    def cleanup_affect(self):
        if self._wins > 0:
            self.frustration = 0
        else:
            self.frustration += self._losses
        self._wins = 0
        self._losses = 0
        self._scheduled = False
