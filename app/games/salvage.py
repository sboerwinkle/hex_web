from .. import board, wait, tasks, vector as vec
from ..game import *
from ..line_of_sight import los_fill
import math
from random import Random

layout = (50, 43, 25, 7)

class Opt:
    def __init__(self, default, handler, descr):
        self.default = default
        self.handler = handler
        self.descr = descr
# Actual list of `Opt`s has to be defined after `SalvageGame`,
# since `handler`s are functions on `SalvageGame`.

class SalvageGame(Game):
    def __init__(self, *a, **kwa):
        super().__init__(*a, tile_type=Tile, **kwa)
        for o in options.values():
            o.handler(self, o.default)
        self.step_complete()
    def seat_player(self, player):
        for c in self.characters:
            if c.abandoned_name == player.name:
                c.set_player(player)
                return
        player.whisper_raw(f">>> Welcome!")
        self.characters.append(SalvageCharacter(self, player))
    def process_command(self, char, cmd):
        # TODO: /click, /grass, /eye
        bits = cmd.split()
        if bits[0] == '/click':
            pos = (int(bits[1]), int(bits[2]))
            char.tile_clicked(pos)
        elif bits[0] == '/grass':
            char.set_mode(MODE_GRASS)
        elif bits[0] == '/eye':
            char.set_mode(MODE_EYE)
        else:
            super().process_command(char, cmd)
    def step_complete(self):
        self.visible_spaces = {}
        for c in self.characters:
            c.do_los()
        super().step_complete()
    def add_visible_spaces(self, spaces):
        d = self.visible_spaces
        for (k, v) in spaces:
            d[k] = v or d.get(k, False)
    def is_occluded(self, pos):
        return len(self.board.get_tile(pos).contents) == 0

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

MODE_GRASS = object()
MODE_EYE = object()

class SalvageCharacter(Character):
    def __init__(self, *a, **kwa):
        self.eyeballs = set()
        self.mode = MODE_EYE
        super().__init__(*a, layout = layout, **kwa)
    def draw_to_board(self, out_board):
        for k in self.game.visible_spaces:
            tile = self.game.board.require_tile(k)
            full_visibility = self.game.visible_spaces[k];
            for ent in tile.contents:
                # TODO some ents may not be drawn depending on `full_visibility`
                # TODO again: Maybe `Entity.draw` should just accept a tile,
                #   and we handle fetching it if there are a positive number of ents?
                ent.draw(out_board)
            if not full_visibility:
                out_board.require_tile(k).add("hex_overlay_gray")
        if self.mode == MODE_GRASS:
            self.player.set_status('{Place Eye|/eye}')
        else:
            self.player.set_status('{Cancel Eye Placement|/grass}')
        return layout
    def owned_ent_added(self, e):
        self.eyeballs.add(e)
    def owned_ent_removed(self, e):
        self.eyeballs.remove(e)
    def do_los(self):
        for e in self.eyeballs:
            self.game.add_visible_spaces(los_fill(self.game.is_occluded, e.pos))
    def set_player(self, p):
        if p is None:
            if self.player is not None:
                self.abandoned_name = self.player.name
        else:
            self.abandoned_name = None
        super().set_player(p)
    def tile_clicked(self, pos):
        tile = self.game.board.get_tile(pos)
        candidate_ent = None
        for e in tile.contents:
            if isinstance(e, Eyeball):
                e._move(None)
                self.mode = MODE_EYE
                break
            if isinstance(e, SpriteEnt):
                candidate_ent = e
        else:
            if candidate_ent is None:
                SpriteEnt("grass", self.game)._move(pos)
            if self.mode == MODE_GRASS:
                if candidate_ent is not None:
                    candidate_ent._move(None)
            else:
                Eyeball(self, self.game)._move(pos)
                self.mode = MODE_GRASS
        self.game.step_complete()
    def set_mode(self, mode):
        self.mode = mode
        self.step_complete()

class Eyeball(OwnedEnt, SpriteEnt):
    def __init__(self, owner, *a, **ka):
        super().__init__(owner, 'hex_eye', *a, **ka)
