from .. import wait, tasks, vector as vec
from ..game import *
import math
from random import Random

TILES_PER_CHAR = 12
DENSITY = 0.3

layout = (31, 31, 0, 0)

path_symbols = {
        'w': ( 0, -1),
        'a': (-1,  0),
        's': ( 0,  1),
        'd': ( 1,  0)
}

teams = (
    ("red", "\U0001F7E5"),
    ("green", "\U0001F7E9"),
    ("blue", "\U0001F7E6"),
    ("yellow", "\U0001F7E8"),
    ("black", "\U00002B1B"),
    ("purple", "\U0001F7EA"),
)

ST_BID = object()
ST_PLAN = object()
ST_RUN = object()
ST_WAIT = object()

def decode_path_symbol(sym):
    try:
        return path_symbols[sym]
    except KeyError:
        raise PebkacException(f"symbol '{sym}' is not valid, must be one of {list(path_symbols.keys())}")

def tile_empty(t):
    for c in t.contents:
        if isinstance(c, SpriteEnt):
            return False
    return True

class Bid:
    def __init__(self, char, spawn_ix, points):
        self.char = char
        self.spawn_ix = spawn_ix
        self.points = points

class PathGame(Game):
    def __init__(self, *a, **kwa):
        super().__init__(*a, **kwa)
        self.rng = Random()
        self.stage = None
        self.task_queue = tasks.MillisTaskQueue(self.step_complete, sec_per_turn = 0.1)
    async def cleanup(self):
        await self.task_queue.cancel()
    def seat_player(self, player):
        for c in self.characters:
            if c.abandoned_name == player.name:
                c.set_player(player)
                return
        for team in teams:
            for c in self.characters:
                if c.team == team:
                    break
            else:
                player.whisper_raw(f">>> You are {team[0]} {team[1]}")
                self.characters.append(PathCharacter(team, self, player))
                return
        player.whisper_raw(f"!!! Sorry, no more than {len(teams)} players are supported, you were not added to the game")
    def begin(self):        
        self.mk_board()
    def process_command(self, char, cmd):
        bits = cmd.split()
        # TODO /kick (For now this will only work for orphaned characters)
        if bits[0] == "/p":
            if self.stage is not ST_PLAN:
                raise PebkacException("/p not allowed now!")
            if len(bits) == 1:
                bits.append("")
            if len(bits) != 2:
                raise PebkacException("/p requires only one arg, e.g. '/p wdsddwawdwaasaw'")
            input_path = bits[1]
            parsed_path = [decode_path_symbol(x) for x in input_path]
            char.instructions = parsed_path
            char.player.whisper_raw("... path confirmed")
            for c in self.characters:
                if c.instructions is None:
                    break
            else:
                self.stage = ST_RUN
                self.task_queue.schedule(self.launch_all_characters, 0, tasks.NO_PATIENCE)
        elif bits[0] == "/n":
            # We also allow going to the next board during the bidding stage,
            # i.e. if everyone agrees they really don't like it or its broken etc.
            # Probably shouldn't do this though, that's the strategic aspect of multi-round bidding.
            if self.stage is not ST_WAIT and self.stage is not ST_BID:
                raise PebkacException("/n not allowed now!")
            self.mk_board()
        elif bits[0] == "/b":
            if self.stage is not ST_BID:
                raise PebkacException("/b not allowed now!")
            bids = [abs(int(x)) for x in bits[1:]]
            if len(bids) != len(self.spawns):
                raise PebkacException(f"Exactly {len(self.spawns)} bids must be specified!")
            total_bid = sum(bids)
            if total_bid > char.pity_points:
                raise PebkacException(f"{total_bid} points bid, but you only have {char.pity_points} points for bidding!")
            # Remove any previous bids from this char (also why we do not subract points now)
            self.bids = list(filter(lambda b: b.char is not char, self.bids))
            self.bids += [Bid(char, i, bids[i]) for i in range(len(self.spawns))]
            char.player.whisper_raw("... bid confirmed")
            if len(self.bids) == len(self.characters) * len(self.spawns):
                self.resolve_bids()
        elif bits[0] == "/help" or bits[0] == "/h":
            f = char.player.whisper_raw
            f('... Available commands are:')
            f('... /b [points_1] [points_2] ...')
            f('...     set your bids on each starting position')
            f('... /p [wasd_letters]')
            f('...     set your path (e.g. /p wdsdd)')
            f('... /n')
            f('...     start a new round')
            f('... /help')
            f('...     this help')
        else:
            super().process_command(char, cmd)
    def launch_all_characters(self):
        for c in self.characters:
            self.task_queue.schedule(c.step, 0, tasks.NO_PATIENCE)

    def legal_wall(self, pos):
        """
        This used to be a lot more complex,
        but it didn't work so well.
        Leaving it for now tho
        """
        return True

        t = self.board.get_tile
        moves = path_symbols.values()
        if not tile_empty(t(pos)):
            raise Exception(f"Shouldn't be asking about the legality of a wall in a filled space: {pos}")
        for a in moves:
            neighbor = vec.add(pos, a)
            if not tile_empty(t(neighbor)):
                continue
            openings = 0
            for b in moves:
                if tile_empty(t(vec.add(neighbor, b))):
                    openings += 1
                    # Walls are legal if they do not create "dead ends" in any of their neighbors
                    if openings == 3:
                        break
            else:
                return False
        return True
    def mk_board(self):
        tile_estimate = len(self.characters) * TILES_PER_CHAR
        height = int(math.sqrt(tile_estimate))
        width = height
        leftover = tile_estimate - width * height
        if leftover > height / 2:
            width = height + 1
            if leftover > height * 1.5 + 0.5:
                height = height + 1
        # +2 so we have space to draw the walls
        self.board.reset(width = width + 2, height = height + 2)

        # This is done outside the game loop,
        # so we can just call _run on our WriteOps directly
        # (Even if that's usually frowned upon)
        for i in range(width+2):
            Move(SpriteEnt("wall", self), (i, 0))._run()
            Move(SpriteEnt("wall", self), (i, height + 1))._run()
        for i in range(height):
            Move(SpriteEnt("wall", self), (0, i + 1))._run()
            Move(SpriteEnt("wall", self), (width + 1, i + 1))._run()
        l = []
        for i in range(width):
            for j in range(height):
                l.append((i + 1, j + 1))
        for _ in range(int(width*height*DENSITY)):
            ix = self.rng.randint(0, len(l) - 1)
            pos = l[ix]
            if not self.legal_wall(pos):
                break
            l.pop(ix)
            Move(SpriteEnt("wall", self), pos)._run()
        self.spawns = []
        for n in range(len(self.characters)):
            pos = l.pop(self.rng.randint(0, len(l)-1))
            self.spawns.append(pos)
            Move(SpriteEnt("sq_num_" + str(n+1), self), pos)._run()
        self.stage = ST_BID
        self.bids = []
        self.step_complete()

    def resolve_bids(self):
        for b in self.bids:
            b.char.pity_points -= b.points
        self.bids.sort(reverse = True, key = lambda b: b.points)
        while self.bids:
            points = self.bids[0].points
            # Find number of bids w/ same amt of points
            cutoff = next((i for i in range(len(self.bids)) if self.bids[i].points < points), len(self.bids))
            winner = self.rng.choice(self.bids[:cutoff])
            self.bids = list(filter(lambda b: b.spawn_ix != winner.spawn_ix and b.char is not winner.char, self.bids))
            if winner.char.player is not None:
                player_name = winner.char.player.name
            else:
                player_name = winner.char.abandoned_name
            self.lobby.broadcast(f">>> {player_name} {winner.char.team[1]} takes position {winner.spawn_ix+1} for {winner.points} points")
            winner.char.avatar_spawn_writeop(self.spawns[winner.spawn_ix])._run()
        self.stage = ST_PLAN
        self.step_complete()

    def check_round_over(self):
        for c in self.characters:
            if c.instructions is not None:
                return
        self.task_queue.schedule(self.finish_round, 0, tasks.ACT_PATIENCE)
    def finish_round(self):
        round_scores = [c.score - c.prev_score for c in self.characters]
        max_score = max(round_scores)
        for c in self.characters:
            c.pity_points += max_score + c.prev_score - c.score
        self.stage = ST_WAIT

class PathCharacter(Character):
    def __init__(self, team, *a, **kwa):
        self.team = team
        self.score = 0
        self.pity_points = 0
        super().__init__(*a, layout = layout, **kwa)

        self.avatar = None
        self.instructions = None
    def avatar_spawn_writeop(self, pos):
        self.instructions = None
        self.score += 1 # For initial space, makes the math more obvious when looking at it
        self.prev_score = self.score
        self.avatar = SpriteEnt("sq_face_1", self.game)
        ops = [
            Move(SpriteEnt("sq_" + self.team[0], self.game), pos),
            Move(self.avatar, pos),
        ]
        for e in self.game.board.get_tile(pos).contents:
            if isinstance(e, SpriteEnt):
                ops.append(Destroy(e))
        return WriteAll(*ops)
    def draw_to_board(self, out_board):
        self.player.set_status(' '.join([f"{c.team[1]}{c.score}({c.pity_points})\xA0\xA0\xA0\xA0" for c in self.game.characters]))
        return super().draw_to_board(out_board)
    def set_player(self, p):
        if p is None:
            if self.player is not None:
                self.abandoned_name = self.player.name
        else:
            self.abandoned_name = None
        super().set_player(p)
    def step(self):
        if 0 == len(self.instructions):
            self.instructions = None
            self.game.check_round_over()
            self.score += 1
            return
        instr = self.instructions.pop(0)
        new_pos = vec.add(self.avatar.pos, instr)
        if not tile_empty(self.game.board.get_tile(new_pos)):
            self.destroy_avatar()
            return

        new_square = SpriteEnt("sq_" + self.team[0], self.game)
        self.movement = WithClaim(
            self.game,
            new_pos,
            WriteAll(Move(new_square, new_pos), Move(self.avatar, new_pos))
        )
        self.movement.sched(self.game.task_queue)
        self.game.task_queue.schedule(self.verify_move, 0, tasks.ACT_PATIENCE)

    def verify_move(self):
        if self.movement.success:
            self.score += 1
            self.game.task_queue.schedule(self.step, 5, tasks.NO_PATIENCE)
        else:
            self.destroy_avatar()

    def destroy_avatar(self):
        self.instructions = None
        self.game.check_round_over()
        Destroy(self.avatar).sched(self.game.task_queue)
