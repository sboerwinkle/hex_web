from .board import *
from .common import *
from . import tasks

class Game:
    def __init__(self):
        self.characters = []
        self.board = Board(tile_type = WatchyTile)
    def seat_player(self, player):
        self.characters.append(Character(self, player))
    def begin(self):
        # Subclasses can use this to do something when the game starts
        pass
    def process_command(self, char, cmd):
        # This will be moved elsewhere eventually, to a subclass or something
        bits = cmd.split()
        if bits[0] == "/tf":
            pos = (int(bits[1]), int(bits[2]))
            tile = self.board.require_tile(pos)
            for e in tile.contents:
                if isinstance(e, SpriteEnt) and e.sprite == "grass":
                    tile.rm(e)
                    break
            else:
                tile.add(SpriteEnt("grass", self, pos))
            self.step_complete()
        else:
            raise PebkacException(f"Unknown command '{bits[0]}'")
    def step_complete(self):
        for c in self.characters:
            c.step_complete()
    async def cleanup(self):
        # Other games may have stuff they wanna do here.
        # Todo change this to use some sort of idiomatic Python cleanup?
        pass

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
                    ent.draw(self, out_board)
        return self.layout

class Ent:
    def __init__(self, game):
        self.game = game
        self.board = game.board
        self.pos = None
    def draw(self, char, out_board):
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
    def draw(self, char, out_board):
        if self.pos is not None:
            # Maybe we ask the `char` if it has any line-of-sight preferences???
            out_board.require_tile(self.pos).add(self.sprite)

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
