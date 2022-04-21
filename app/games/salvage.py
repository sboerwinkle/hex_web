from .. import board, wait, tasks, vector as vec
from ..game import *
from ..line_of_sight import los_fill
from ..path_planning import update_path
import math
from random import Random

layout = (50, 43, 25, 7, 'hex_empty')

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
        self.phase = init_phase
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
        elif bits[0] == '/home':
            char.path_home()
        elif bits[0] == '/step':
            char.manual_step(int(bits[1]))
        elif bits[0] == '/clear':
            char.clear_steps()
        elif bits[0] == '/done':
            self.complete_phase()
        else:
            super().process_command(char, cmd)
    def step_complete(self):
        self.visible_spaces = {}
        for c in self.characters:
            c.do_los()
        super().step_complete()

    def new_phase(self, phase):
        # TODO: This function might have recursion problems;
        #       right now it's avoided since basically every phase is going to get hung up on player input
        #       (and there aren't any AI to render decisions before `reqd_units` is updated)
        self.phase = phase
        self.ready_units = set()
        self.reqd_units = set()
        self.reqd_units = phase.reqd_units(self) #Should probably also update units with what their requirement is
        if (len(self.reqd_units) == 0):
            # Hopefully this doesn't result in *too* much recursion, hahaha...
            self.resolve_phase()
            return
        self.step_complete()
    def complete_phase(self):
        self.new_phase(self.phase.complete(self))
    def update_unit_readiness(self, unit, ready):
        if not ready:
            self.ready_units.remove(unit)
            return
        if unit not in self.reqd_units:
            raise Exception("Unit readied up, but isn't required for this phase!");
        self.ready_units.add(unit)
        if len(self.ready_units) == len(self.reqd_units):
            self.complete_phase()

    def add_visible_spaces(self, spaces):
        d = self.visible_spaces
        for (k, v) in spaces:
            d[k] = max(v, d.get(k, 0))
    def is_opaque(self, pos):
        stuff = self.board.get_tile(pos).contents
        if len(stuff) == 0:
            return True
        for e in stuff:
            if isinstance(e, SpriteEnt) and e.sprite == "hex_wall":
                return True
        return False
    def is_walkable(self, pos):
        # Eventually this will also have to return false for
        # enemy units etc. We could friendly units as walkable
        # because they will all update position simultaneously,
        # and those "collisions" are handled separately
        return not self.is_opaque(pos)
    def plannable(self, pos):
        if pos not in self.visible_spaces:
            return True
        return self.is_walkable(pos)
    def run_paths(self):
        destinations = {}
        to_resolve = []
        def place(person, step, handicap):
            dest = person.pos if step == -1 else person.path[step][0]
            try:
                l = destinations[dest]
            except KeyError:
                l = []
                destinations[dest] = l
            if len(l) == 1:
                to_resolve.append(dest)
            l.append((person, (step, handicap)))
        for c in self.characters:
            for e in c.eyeballs:
                i = -1
                path = e.path
                for i in range(len(path)):
                    if not self.is_walkable(path[i][0]):
                        i -= 1
                        break
                place(e, i, 0)
        while to_resolve:
            to_place = []
            for d in to_resolve:
                competitors = destinations[d]
                winner = None
                # `competitors` will be non-empty,
                # this just creates a `best` that the first person will always beat.
                best = (competitors[0][1][0] + 1, 0)
                for item in competitors:
                    score = item[1]
                    if score < best:
                        best = score
                        winner = item
                    elif score == best:
                        winner = None
                if winner:
                    competitors.remove(winner)
                    destinations[d] = [winner]
                else:
                    destinations[d] = []
                to_place += competitors
            to_resolve = []
            for person, score in to_place:
                place(person, score[0] - 1, score[1] - 1)
        for d in destinations:
            for person, _ in destinations[d]:
                person._move(d)
                person.path = []

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
MAX_PATH = 4

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
        status_line = '{Complete|/done}'
        if self.selected is not None:
            out_board.require_tile(self.selected.pos).add("hex_select")
            for p, _ in self.selected.path:
                # Originally I was going to outline the path arrows of
                # the selected person, but that's like 6 more sprites
                # and I don't wanna draw those.
                out_board.require_tile(p).add("hex_select")
            status_line += ' {Remove|/rm} {Return|/home}'
        elif self.mode == MODE_DEFAULT:
            status_line += ' {Place Eye|/eye}'
        else:
            status_line += ' {Cancel Eye Placement|/eye}'
        self.player.set_status(status_line)
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
            self.game.add_visible_spaces(los_fill(self.game.is_opaque, e.pos))
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
            self.selected = None
            s.rm_watcher(self.select_watch)
            if pos == s.pos:
                # Just deselect, don't need to update everyone
                self.step_complete()
            else:
                s.path = update_path(s.pos, s.path, MAX_PATH, pos, self.game.plannable)
                self.game.step_complete()
            # TODO This might trigger an additional client frame, making the previous one unnecessary. Oh well?
            if s.move_reqd:
                self.game.update_unit_readiness(s, True)
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
    def manual_step(self, angle):
        if self.selected is None:
            raise PebkacException("Nothing selected, cannot step!")
        path = self.selected.path
        if len(path) >= MAX_PATH:
            raise PebkacException("Path too long, cannot step!")
        start = path[-1][0] if len(path) else self.selected.pos
        path.append((vec.add(start, vec.units[angle]), angle))
        self.game.step_complete()
    def clear_steps(self):
        if self.selected is None:
            raise PebkacException("Nothing selected, cannot clear!")
        self.selected.path = []
        self.game.step_complete()
    def path_home(self):
        s = self.selected
        if s is None:
            raise PebkacException("Nothing selected, cannot go home!")
        self.selected = None
        s.rm_watcher(self.select_watch)
        s.path = update_path(s.pos, s.path, MAX_PATH, s.pos, self.game.plannable)
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
        self.move_reqd = False
        self.path = []
        self.vote_options = None
        self.vote = None
        super().__init__('hex_eye', *a, **ka)

## Phases (mostly this is the larger-scale game logic)

# Surely python has a better solution than these wacky singletons?

class VoteyPhase:
    def reqd_units(self, game):
        result = set()
        for c in game.characters:
            result.update(c.eyeballs)
            for e in c.eyeballs:
                e.vote = None
                e.vote_options = ['Yes', 'No']
        return result
    def complete(self, game):
        d = 0
        for c in game.characters:
            for e in c.eyeballs:
                if e.vote == 'Yes':
                    d += 1
                elif e.vote == 'No':
                    d -= 1
                e.vote = None
                e.vote_options = None
        if d == 0:
            result = "It's a tie!"
        elif d > 0:
            result = "'Yes' wins"
        else:
            result = "'No' wins"
        game.lobby.broadcast(result)
        return movey_phase
votey_phase = VoteyPhase()

class MoveyPhase:
    def reqd_units(self, game):
        result = set()
        for c in game.characters:
            result.update(c.eyeballs)
            for e in c.eyeballs:
                e.path = []
                e.move_reqd = True
        return result
    def complete(self, game):
        for c in game.characters:
            for e in c.eyeballs:
                e.move_reqd = False
        game.run_paths()
        return votey_phase
movey_phase = MoveyPhase()

class InitPhase:
    def reqd_units(self, game):
        raise Exception("InitPhase should never be transitioned to!")
    def complete(self, game):
        game.lobby.broadcast("Game begins.")
        return votey_phase
init_phase = InitPhase()
