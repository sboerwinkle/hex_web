from .board import *
from .common import *
from . import tasks

# Minimal impl of a Game, no amenities or bells and whistles
class BareGame:
    def __init__(self, lobby):
        self.lobby = lobby
    def seat_player(self, player):
        pass
    def process_command(self, char, cmd):
        # This will only be invoked if the player issuing the command
        # has an associated character (`char`)
        pass
    def begin(self):
        # Subclasses can use this to do something when the game starts
        pass
    async def cleanup(self):
        # Other games may have stuff they wanna do here.
        # Todo change this to use some sort of idiomatic Python cleanup?
        pass

class Game(BareGame):
    def __init__(self, *a, tile_type = WatchyTile, **ka):
        super().__init__(*a, **ka)
        self.characters = []
        self.board = Board(tile_type = tile_type)
    def seat_player(self, player):
        self.characters.append(Character(self, player))
    def process_command(self, char, cmd):
        raise PebkacException(f"Unknown command '{cmd.split()[0]}'")
    def step_complete(self):
        for c in self.characters:
            c.step_complete()

# Borrowing terminology from DnD, a "Player" is the human, and a "Character" is the in-game avatar.
# Characters have game-state data, and can be associated (or disassociated) with a player due to any number of things:
# Network issues, save/load, swapping seats, etc.
# Neither is especially concerned with the impl of the other, though they will have some interface.
class Character:
    def __init__(self, game, player, layout):
        self.game = game
        self.layout = layout
        self.player = None
        self.set_player(player)
    def set_player(self, p):
        self.player = p
        if p is not None:
            p.set_char(self)
    def step_complete(self):
        if self.player != None:
            self.player.do_frame()
    def draw_to_board(self, out_board):
        # Access entire raw board, ignoring coords
        for col in self.game.board.board:
            for cell in col:
                for ent in cell.contents:
                    ent.draw(out_board)
        return self.layout

class Ent:
    def __init__(self, game):
        self.game = game
        self.board = game.board
        self.pos = None
    def draw(self, out_board):
        pass
    # TODO Maybe some standard way to get qualitative information about what it is???
    # qualia(self) -> Qualia (???)
    def _destroy(self):
        self._move(None)
        self.game = None
        self.board = None
    def _move(self, pos):
        if self.pos is not None:
            self.board.get_tile(self.pos).rm(self)
        if pos is not None:
            self.board.require_tile(pos).add(self)
        self.pos = pos

class SpriteEnt(Ent):
    def __init__(self, sprite, *a, **kwa):
        self.sprite = sprite
        super().__init__(*a, **kwa)
    def draw(self, out_board):
        if self.pos is not None:
            out_board.require_tile(self.pos).add(self.sprite)

class WatchedEnt(Ent):
    def __init__(self, *a, **kwa):
        self.watchers = []
        super().__init__(*a, **kwa)
    def add_watcher(self, w):
        self.watchers.append(w)
        if self.pos is not None:
            w(self)
    def rm_watcher(self, w):
        self.watchers.remove(w)
    def _move(self, pos):
        fire = (pos is None) != (self.pos is None)
        super()._move(pos)
        if fire:
            for w in self.watchers.copy():
                w(self)

class WriteOp:
    """
    Basically just an operation that writes public state
    and needs to be careful to not muck things up
    """
    def sched(self, q):
        q.schedule(self._run, 0, tasks.WRITE_PATIENCE)

class Move(WriteOp):
    def __init__(self, ent, pos):
        self.ent = ent
        self.pos = pos
    def _run(self):
        self.ent._move(self.pos)

class Destroy(WriteOp):
    def __init__(self, ent):
        self.ent = ent
    def _run(self):
        self.ent._destroy()

class WriteAll(WriteOp):
    def __init__(self, *a):
        self.args = a
    def _run(self):
        for a in self.args:
            a._run()

class WithClaim(WriteOp):
    def __init__(self, game, pos, op):
        self.game = game
        self.pos = pos
        self.op = op
    def _run(self):
        self.tok = ClaimToken(self.game)
        Move(self.tok, self.pos)._run()
        self.game.task_queue.schedule(self.resolve, 0, tasks.NO_PATIENCE)
    def resolve(self):
        Destroy(self.tok)._run()
        # For use by whoever created me
        self.success = self.tok.valid
        if self.success:
            self.op._run()

# Eventually these may be more complex, e.g. a heirarchy of "stronger" tokens / claiming different aspects of the tile,
# but for now just making sure nobody else is interested in the tile is enough.
class ClaimToken(Ent):
    def __init__(self, *a, **kwa):
        super().__init__(*a, **kwa)
        self.valid = True
    def _move(self, pos):
        if pos is not None:
            for e in self.board.get_tile(pos).contents:
                if isinstance(e, ClaimToken):
                    e.valid = False
                    self.valid = False
        super()._move(pos)
