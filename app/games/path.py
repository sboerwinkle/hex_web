from .. import wait, tasks, vector as vec
from ..game import *
import math
from random import Random

layout = (31, 31, 0, 0, 'sq_empty')

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
        if isinstance(c, SolidEnt):
            return False
    return True

def simple_scoring(tiles, points):
    return [points * t for t in tiles]

def ratio_scoring(tiles, points):
    first = max(tiles)
    return [points * t // first for t in tiles]

def pool_scoring(tiles, points):
    total = sum(tiles)
    ans = [points * t // total for t in tiles]
    missing = points - sum(ans)
    # We really want to prioritize by `ans[i]/points - tiles[i]/total` (which is <= 0),
    # but since we don't trust floating point numbers we make them integers by
    # multiplying by `points*total`
    priorities = [(i, ans[i]*total - tiles[i]*points) for i in range(len(tiles))]
    priorities.sort(key = lambda x: x[1])
    # We don't want to give spare points unequally to people who were
    # the same distance from achieving their next point,
    # so if the boundary is between people with the same priority throw a point out
    while missing and priorities[missing][1] == priorities[missing-1][1]:
        missing -= 1
    for i in range(missing):
        ans[priorities[i][0]] += 1
    return ans

class Opt:
    def __init__(self, default, handler, descr):
        self.default = default
        self.handler = handler
        self.descr = descr
# Actual list of `Opt`s has to be defined after `PathGame`,
# since `handler`s are functions on `PathGame`.

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
        for o in options.values():
            o.handler(self, o.default)
    def set_scoring(self, value):
        if value == "simple":
            self.scoring = simple_scoring
        elif value == "ratio":
            self.scoring = ratio_scoring
        elif value == "pool":
            self.scoring = pool_scoring
        else:
            raise PebkacException("Not a valid input")
    def set_points(self, value):
        try:
            self.points = int(value)
        except ValueError:
            raise PebkacException("Input must be an integer")
    def set_head_tiles(self, value):
        try:
            self.head_tiles = int(value)
        except ValueError:
            raise PebkacException("Input must be an integer")
    def set_tiles_per_char(self, value):
        try:
            self.tiles_per_char = float(value)
        except ValueError:
            raise PebkacException("Input must be a decimal")
    def set_wall_density(self, value):
        try:
            self.wall_density = float(value)
        except ValueError:
            raise PebkacException("Input must be a decimal")
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
        self.lobby.broadcast(">>> Game setup complete. Use /help for info on commands, or /rules for a longer description of how to play")
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
            self.lobby.broadcast(f">>> {char.player.name} path set")
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
            self.lobby.broadcast(f">>> {char.player.name} bid set")
            if len(self.bids) == len(self.characters) * len(self.spawns):
                self.resolve_bids()
        elif bits[0] == "/set":
            if len(bits) == 1:
                f = char.player.whisper_raw
                f('... Run "/set [opt]" for more info on an option,')
                f('... or "/set [opt] [val]" to set a value.')
                f('... Options are:')
                f('... ' + ", ".join(options))
                f('')
            else:
                try:
                    o = options[bits[1]]
                except KeyError:
                    raise PebkacException(f"Invalid option name '{bits[1]}'")
                if len(bits) == 2:
                    f = char.player.whisper_raw
                    for line in o.descr.split('\n'):
                        f('... ' + line)
                    f(f"... (default is '{o.default}')")
                    f('')
                elif len(bits) == 3:
                    o.handler(self, bits[2])
                    self.lobby.broadcast(f">>> {char.player.name} issued '{cmd}'")
                else:
                    raise PebkacException("Too many arguments to /set!")
        elif bits[0] == "/help" or bits[0] == "/h":
            f = char.player.whisper_raw
            f('... Available commands are:')
            f('... /b [points_1] [points_2] ...')
            f('...     set your bids on each starting position')
            f('... /p [wasd_letters]')
            f('...     set your path (e.g. /p wdsdd)')
            f('... /n')
            f('...     start a new round')
            f('... /set')
            f('...     sets game options; run by itself for more info')
            f('... /help')
            f('...     this help')
            f('... /rules')
            f('...     info on how to play')
            f('')
        elif bits[0] == "/rules":
            f = char.player.whisper_raw
            f('... Synopsis of commands is available in /help.')
            f('... Broadly your goal is to get points by covering the board.')
            f('... Not running into anything is worth 3 tiles by default.')
            f('... When other people get more points than you, you earn pity-points -')
            f('... These are spent during the bidding phase (/b) of next round to get a better spot.')
            f('... Initially nobody has any pity-points, so everyone will have to bid zeroes, e.g.:')
            f('... /b 0 0 0')
            f('... Once places are chosen, set a path (/p) that will probably not run into people.')
            f('... Feel free to talk and threaten!')
            f('... Paths are written with the WASD keys, e.g.:')
            f('... /p ddwaa')
            f('... Once everything is decided, anyone can advance to the next round (/n).')
            f('... When you hit the agreed-upon number of rounds, or you get tired,')
            f('... whoever has the most points wins! Pity-points do not count for victory.')
            f('')
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
        tile_estimate = len(self.characters) * self.tiles_per_char
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
            Move(SolidEnt("wall", self), (i, 0))._run()
            Move(SolidEnt("wall", self), (i, height + 1))._run()
        for i in range(height):
            Move(SolidEnt("wall", self), (0, i + 1))._run()
            Move(SolidEnt("wall", self), (width + 1, i + 1))._run()
        l = []
        for i in range(width):
            for j in range(height):
                l.append((i + 1, j + 1))
        for _ in range(int(width*height*self.wall_density)):
            ix = self.rng.randint(0, len(l) - 1)
            pos = l[ix]
            if not self.legal_wall(pos):
                break
            l.pop(ix)
            Move(SolidEnt("wall", self), pos)._run()
        self.spawns = []
        for n in range(len(self.characters)):
            pos = l.pop(self.rng.randint(0, len(l)-1))
            self.spawns.append(pos)
            Move(SolidEnt("sq_num_" + str(n+1), self), pos)._run()
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
            self.lobby.broadcast(f">>> {player_name} {winner.char.team[1]} takes position {winner.spawn_ix+1} for {winner.points} pity-points")
            winner.char.avatar_spawn_writeop(self.spawns[winner.spawn_ix])._run()
        self.stage = ST_PLAN
        self.step_complete()

    def check_round_over(self):
        for c in self.characters:
            if c.instructions is not None:
                return
        self.task_queue.schedule(self.finish_round, 0, tasks.ACT_PATIENCE)
    def finish_round(self):
        round_scores = self.scoring([c.tiles for c in self.characters], self.points)
        max_score = max(round_scores)
        for (c, score) in zip(self.characters, round_scores):
            if c.player is not None:
                player_name = c.player.name
            else:
                player_name = c.abandoned_name
            self.lobby.broadcast(f">>> {player_name} {c.team[1]} got {score} points for {c.tiles} tiles")
            c.score += score
            c.pity_points += max_score - score
        self.stage = ST_WAIT

options = {
    'scoring': Opt(
        'simple',
        PathGame.set_scoring,
        '"simple": Each tile is worth points'
        + '\n"ratio": Points depend on how many tiles you got compared to 1st place'
        + '\n"pool": A fixed pool of points is alotted each round'
    ),
    'points': Opt(
        '1',
        PathGame.set_points,
        'Meaning depends on what "scoring" is set to:'
        + '\n"simple": Points per tile'
        + '\n"ratio": How many points 1st place gets'
        + '\n"pool": How many points in the pool'
    ),
    'head_tiles': Opt(
        '3',
        PathGame.set_head_tiles,
        'How many tiles it is worth to not run into anything (keep your head)'
    ),
    'tiles_per_char': Opt(
        '12',
        PathGame.set_tiles_per_char,
        'Roughly how many tiles should be on the board per character'
    ),
    'wall_density': Opt(
        '0.3',
        PathGame.set_wall_density,
        'What ratio of the tiles on the board should be walls'
    )
}

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
        self.tiles = 1 # For initial space, makes the math more obvious when looking at it
        self.avatar = SpriteEnt("sq_face_1", self.game)
        ops = [
            Move(SolidEnt("sq_" + self.team[0], self.game), pos),
            Move(self.avatar, pos),
        ]
        for e in self.game.board.get_tile(pos).contents:
            if isinstance(e, SolidEnt):
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
            self.tiles += self.game.head_tiles
            return
        instr = self.instructions.pop(0)
        new_pos = vec.add(self.avatar.pos, instr)
        if not tile_empty(self.game.board.get_tile(new_pos)):
            self.destroy_avatar()
            return

        new_square = SolidEnt("sq_" + self.team[0], self.game)
        self.movement = WithClaim(
            self.game,
            new_pos,
            WriteAll(Move(new_square, new_pos), Move(self.avatar, new_pos))
        )
        self.movement.sched(self.game.task_queue)
        self.game.task_queue.schedule(self.verify_move, 0, tasks.ACT_PATIENCE)

    def verify_move(self):
        if self.movement.success:
            self.tiles += 1
            self.game.task_queue.schedule(self.step, 5, tasks.NO_PATIENCE)
        else:
            Move(SpriteEnt("sq_mess", self.game), self.movement.pos).sched(self.game.task_queue)
            self.destroy_avatar()

    def destroy_avatar(self):
        self.instructions = None
        self.game.check_round_over()
        Destroy(self.avatar).sched(self.game.task_queue)

# Just a subclass we use with `isinstance`, no code difference
class SolidEnt(SpriteEnt):
    pass
