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
        for y in range(0, 7):
            for x in range(-(y//2), 8 + (-y//2)):
                SpriteEnt("grass", self)._move((x,y))
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
        bits = cmd.split()
        if bits[0] == '/click':
            pos = (int(bits[1]), int(bits[2]))
            char.tile_clicked(pos)
        elif bits[0] == '/wall':
            char.set_mode(MODE_WALL)
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
            d[k] = max(v, d.get(k, 0))
    def is_occluded(self, pos):
        stuff = self.board.get_tile(pos).contents
        if len(stuff) == 0:
            return True
        for e in stuff:
            if isinstance(e, SpriteEnt) and e.sprite == "hex_wall":
                return True
        return False

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

MODE_WALL = object()
MODE_EYE = object()

class SalvageCharacter(Character):
    def __init__(self, *a, **kwa):
        self.eyeballs = set()
        self.mode = MODE_EYE
        super().__init__(*a, layout = layout, **kwa)
    def draw_to_board(self, out_board):
        for k in self.game.visible_spaces:
            tile = self.game.board.require_tile(k)
            visibility = self.game.visible_spaces[k];
            for ent in tile.contents:
                # TODO some ents may not be drawn depending on `visibility`
                # TODO again: Maybe `Entity.draw` should just accept a tile,
                #   and we handle fetching it if there are a positive number of ents?
                ent.draw(out_board)
            if visibility == 1:
                out_board.require_tile(k).add("hex_overlay_white")
            elif visibility == 2:
                out_board.require_tile(k).add("hex_overlay_light_white")
        if self.mode == MODE_WALL:
            self.player.set_status('{Place Eye|/eye}')
        else:
            self.player.set_status('{Cancel Eye Placement|/wall}')
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
        if len(tile.contents) == 0:
            return
        for e in tile.contents:
            if isinstance(e, Eyeball):
                e._move(None)
                self.mode = MODE_EYE
                break
            if isinstance(e, SpriteEnt) and e.sprite == "hex_wall":
                e._move(None)
                self.mode = MODE_WALL
                break
        else:
            if self.mode == MODE_WALL:
                new_ent = SpriteEnt("hex_wall", self.game)
            else:
                new_ent = Eyeball(self, self.game)
                self.mode = MODE_WALL
            new_ent._move(pos)
        self.game.step_complete()
    def set_mode(self, mode):
        self.mode = mode
        self.step_complete()

class Eyeball(OwnedEnt, SpriteEnt):
    def __init__(self, owner, *a, **ka):
        super().__init__(owner, 'hex_eye', *a, **ka)
