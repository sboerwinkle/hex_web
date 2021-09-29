from . import vector as vec

class Tile:
    def __init__(self):
        self.contents = []
    def add(self, ent):
        self.contents.append(ent)
    def rm(self, ent):
        self.contents.remove(ent)

class WatchyTile(Tile):
    def __init__(self):
        super().__init__()
        self.watchers = []
    def add(self, ent):
        super().add(ent)
        self.handle_activity(ent)
    def rm(self, ent):
        super().rm(ent)
        self.handle_activity(ent)
    def handle_activity(self, ent):
        # tile_update() sometimes cleans up watchers (while we're iterating it!),
        # so we have to make a quick dupe
        for l in self.watchers.copy():
            l.tile_update()

class Board:
    def __init__(self, tile_offset=(0,0), width=1, height=1, tile_type=Tile):
        # tile_offset can also be `None`, which creates a board floating at an unknown position;
        # the first required tile will become (0,0).

        # Should always be initialized with at least 1 tile, so len(board[0]) is valid
        self.tile_type = tile_type
        self.tile_offset = tile_offset
        self.board = [self.mk_tile_list(height) for i in range(width)]
        self.filler = tile_type()

        self.min_x = None
        self.min_y = None
        self.max_x = None
        self.max_y = None

    def get_tile(self, pos):
        if self.min_x == None:
            return self.filler
        (x, y) = vec.sub(pos, self.tile_offset)
        if x < 0 or x >= len(self.board):
            return self.filler
        row = self.board[x]
        if y < 0 or y >= len(row):
            return self.filler
        return row[y]

    def require_tile(self, pos):
        if self.min_x == None:
            self.min_x = pos[0]
            self.max_x = pos[0] + 1
            self.min_y = pos[1]
            self.max_y = pos[1] + 1
            if self.tile_offset == None:
                self.tile_offset = pos
        else:
            if pos[0] < self.min_x:
                self.min_x = pos[0]
            elif pos[0] >= self.max_x:
                self.max_x = pos[0] + 1
            if pos[1] < self.min_y:
                self.min_y = pos[1]
            elif pos[1] >= self.max_y:
                self.max_y = pos[1] + 1

        (x, y) = vec.sub(pos, self.tile_offset)
        width = len(self.board)
        height = len(self.board[0])
        if x < 0:
            self.tile_offset = (pos[0], self.tile_offset[1])
            self.board = [self.mk_tile_list(height) for i in range(-x)] + self.board
            x = 0
        elif x >= width:
            self.board += [self.mk_tile_list(height) for i in range(x - width + 1)]
        if y < 0:
            self.tile_offset = (self.tile_offset[0], pos[1])
            amt = -y
            for i in range(len(self.board)): # Cannot use 'width' here, possibly invalidated by x-axis expansion
                self.board[i] = self.mk_tile_list(amt) + self.board[i]
            y = 0
        elif y >= height:
            amt = y - height + 1
            for col in self.board:
                col += self.mk_tile_list(amt)
        return self.board[x][y]

    def mk_tile_list(self, n):
        return [self.tile_type() for i in range(n)]
