from .. import wait, tasks, vector as vec
from ..game import *
import math
from random import Random

layout = (31, 31, 0, 0)

teams = (
    ("red", "\U0001F7E5"),
    ("green", "\U0001F7E9"),
    ("blue", "\U0001F7E6"),
    ("yellow", "\U0001F7E8"),
    ("black", "\U00002B1B"),
    ("purple", "\U0001F7EA"),
)

class Opt:
    def __init__(self, default, handler, descr):
        self.default = default
        self.handler = handler
        self.descr = descr
# Actual list of `Opt`s has to be defined after `SalvageGame`,
# since `handler`s are functions on `SalvageGame`.

class SalvageGame(Game):
    def __init__(self, *a, **kwa):
        super().__init__(*a, **kwa)
        self.rng = Random()
        for o in options.values():
            o.handler(self, o.default)
    def seat_player(self, player):
        for c in self.characters:
            if c.abandoned_name == player.name:
                c.set_player(player)
                return
        player.whisper_raw(f">>> (...) Welcome!")
        self.characters.append(SalvageCharacter(self, player))
    def begin(self):
        self.lobby.broadcast(">>> (...) Initialized")
    def process_command(self, char, cmd):
        super().process_command(char, cmd)
    def launch_all_characters(self):
        for c in self.characters:
            self.task_queue.schedule(c.step, 0, tasks.NO_PATIENCE)

options = {}
"""
options = {
    'scoring': Opt(
        'simple',
        PathGame.set_scoring,
        '"simple": Each tile is worth points'
        + '\n"ratio": Points depend on how many tiles you got compared to 1st place'
        + '\n"pool": A fixed pool of points is alotted each round'
    ),
}
"""

class SalvageCharacter(Character):
    def __init__(self, *a, **kwa):
        super().__init__(*a, layout = layout, **kwa)
    def draw_to_board(self, out_board):
        out_board.require_tile((1,1)).add("sq_magenta")
        return layout
        #self.player.set_status(' '.join([f"{c.team[1]}{c.score}({c.pity_points})\xA0\xA0\xA0\xA0" for c in self.game.characters]))
    def set_player(self, p):
        if p is None:
            if self.player is not None:
                self.abandoned_name = self.player.name
        else:
            self.abandoned_name = None
        super().set_player(p)
