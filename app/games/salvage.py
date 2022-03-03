from .. import board, wait, tasks, vector as vec
from ..game import *
from ..line_of_sight import los_fill
from ..path_planning import update_path
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
        elif bits[0] == '/rm':
            char.rm_selected()
        elif bits[0] == '/eye':
            char.toggle_eye()
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
    def plannable(self, pos):
        if pos not in self.visible_spaces:
            return True
        return not self.is_occluded(pos)

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

MODE_DEFAULT = object()
MODE_EYE = object()

class SalvageCharacter(Character):
    def __init__(self, *a, **kwa):
        self.eyeballs = set()
        self.mode = MODE_EYE
        self.selected = None
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
        for c in self.game.characters:
            for e in c.eyeballs:
                for p, d in e.path:
                    out_board.require_tile(p).add(f"hex_arrow_{d}")
        if self.selected is not None:
            out_board.require_tile(self.selected.pos).add("hex_select")
            self.player.set_status('{Remove|/rm}')
        elif self.mode == MODE_DEFAULT:
            self.player.set_status('{Place Eye|/eye}')
        else:
            self.player.set_status('{Cancel Eye Placement|/eye}')
        return layout
    def eye_watch(self, e):
        if e.pos is not None:
            self.eyeballs.add(e)
        else:
            self.eyeballs.remove(e)
    def select_watch(self, e):
        if e.pos is not None:
            self.selected = e
        else:
            self.selected = None
            e.rm_watcher(self.select_watch)
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
            # Clicks outside the game board are completely ignored
            return
        s = self.selected
        if s is not None:
            if pos == s.pos:
                self.selected = None
                s.rm_watcher(self.select_watch)
                self.step_complete()
            else:
                s.path = update_path(s.pos, s.path, 3, pos, self.game.plannable)
                self.game.step_complete()
        else:
            for e in tile.contents:
                if isinstance(e, Eyeball):
                    e.add_watcher(self.select_watch)
                    self.mode = MODE_DEFAULT
                    self.step_complete()
                    return
                if isinstance(e, SpriteEnt) and e.sprite == "hex_wall":
                    e._move(None)
                    self.mode = MODE_DEFAULT
                    self.game.step_complete()
                    return
            if self.mode == MODE_DEFAULT:
                new_ent = SpriteEnt("hex_wall", self.game)
            else:
                new_ent = Eyeball(self.game)
                new_ent.add_watcher(self.eye_watch)
                self.mode = MODE_DEFAULT
            new_ent._move(pos)
            self.game.step_complete()
    def rm_selected(self):
        if self.selected is None:
            raise PebkacException("Nothing selected, cannot remove!")
        self.selected._move(None)
        self.game.step_complete()
    def toggle_eye(self):
        self.mode = MODE_EYE if self.mode == MODE_DEFAULT else MODE_DEFAULT
        self.step_complete()

class Eyeball(WatchedEnt, SpriteEnt):
    def __init__(self, *a, **ka):
        self.path = []
        super().__init__('hex_eye', *a, **ka)
