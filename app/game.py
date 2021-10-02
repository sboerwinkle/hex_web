from .board import *
from .common import *

class Game:
    def __init__(self):
        self.characters = []
        self.board = Board(tile_type = WatchyTile)
    def seat_player(self, player):
        self.characters.append(Character(self, player))
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
    def __init__(self, game, pos):
        self.game = game
        self.board = game.board
        self.pos = pos
        self.board.require_tile(pos).add(self)
    def draw(self, char, out_board):
        pass
    # TODO Maybe some standard way to get qualitative information about what it is???
    # qualia(self) -> Qualia (???)
    def destroy(self):
        self.board.get_tile(self.pos).rm(self)
        self.game = None
        self.board = None
    def move(self, pos):
        self.board.get_tile(self.pos).rm(self)
        self.board.require_tile(pos).add(self)
        self.pos = pos

class SpriteEnt(Ent):
    def __init__(self, sprite, *a, **kwa):
        self.sprite = sprite
        super().__init__(*a, **kwa)
    def draw(self, char, out_board):
        # Maybe we ask the `char` if it has any line-of-sight preferences???
        out_board.require_tile(self.pos).add(self.sprite)
