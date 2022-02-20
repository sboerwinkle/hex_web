from .. import wait, tasks
from ..game import *

class TendGame(Game):
    def __init__(self):
        super().__init__()
        self.task_queue = tasks.MillisTaskQueue(self.step_complete)
    async def cleanup(self):
        await self.task_queue.cancel()
    def seat_player(self, player):
        new_char = GrowCharacter(self, player)
        self.characters.append(new_char)
        return new_char
    def process_command(self, char, cmd):
        bits = cmd.split()
        if bits[0] == "/mag_pl":
            pos = (int(bits[1]), int(bits[2]))
            tile = self.board.get_tile(pos)
            has_grass = False
            for e in tile.contents:
                if isinstance(e, SpriteEnt) and e.sprite == "grass":
                    has_grass = True
                elif isinstance(e, MagentaPlant):
                    raise PebkacException("Something is already growing there")
            if not has_grass:
                raise PebkacException("Nothing plantable there!")
            delay = int(bits[3]) if len(bits) > 3 else 2000
            tile.add(MagentaPlant(delay, self, pos))
            self.step_complete()
            return
        if bits[0] == "/click":
            pos = (int(bits[1]), int(bits[2]))
            tile = self.board.get_tile(pos)
            has_grass = False
            plant = None
            for e in tile.contents:
                if not has_grass and isinstance(e, SpriteEnt) and e.sprite == "grass":
                    has_grass = True
                elif isinstance(e, MagentaPlant):
                    plant = e
                    break
            if plant != None:
                if plant.stage != 3:
                    raise PebkacException("Not ready for harvest!")
                plant.destroy()
                char.coins += 2
            elif has_grass:
                if char.coins < 1:
                    raise PebkacException("Planting costs a coin!")
                char.coins -= 1
                tile.add(MagentaPlant(2000, self, pos))
            else:
                tile = self.board.require_tile(pos)
                if char.coins < 5:
                    raise PebkacException("Creating land costs 5 coins!")
                char.coins -= 5
                tile.add(SpriteEnt("grass", self, pos))
            self.step_complete()
            return
        if bits[0] == "/coins":
            char.coins = int(bits[1])
            self.step_complete() # TODO This method is more aptly named `write_state` or something...
            return
        super().process_command(char, cmd)

class GrowCharacter(Character):
    def __init__(self, *a, **kwa):
        self.coins = 6
        super().__init__(*a, **kwa)
        if self.player != None:
            self.player.whisper_raw(">>> Click on the board to get started!")
    def draw_to_board(self, out_board):
        # Coin emoji
        self.player.set_status(f"\U0001FA99{self.coins}")
        super().draw_to_board(out_board)

class MagentaPlant(Ent):
    def __init__(self, delay, *a, **kwa):
        super().__init__(*a, **kwa)
        self.delay = delay
        self.stage = 1
        self.game.task_queue.schedule(self.grow, self.delay, tasks.NO_PATIENCE)
    def draw(self, out_board):
        out_board.require_tile(self.pos).add("mag_pl_" + str(self.stage))
    def grow(self):
        if self.game == None:
            return
        self.stage += 1
        if self.stage < 3:
            self.game.task_queue.schedule(self.grow, self.delay, tasks.NO_PATIENCE)

class CoverPlant(Ent):
    max_stage = 3
    def __init__(self, delay, sprite_base, *a, rotation = 0, **ka):
        super().__init__(*a, **ka)
        self.delay = delay
        self.sprite_base = sprite_base
        self.rotation = 0
        self.stage = 1
        self.scheduler = RegularScheduler(self)
        self.scheduler.sched(self.develop, self.get_delay())
    def destroy(self):
        self.scheduler.destroy()
        super().destroy()
    def get_delay(self):
        # TODO This should be weird and more complicated
        return self.delay
    def draw(self, out_board):
        out_board.require_tile(self.pos).add(self.sprite_base + str(self.stage))
    def develop(self):
        self.stage += 1
        method = self.develop if self.stage < self.max_stage else self.try_spawn
        self.scheduler.sched(method, self.get_delay())
    def try_spawn(self):
        self.stage = self.max_stage + 1
        self.scheduler.claim(area_adjacent(self.rotation), ground_cover_claim, self.do_spawn)
    def do_spawn(self, tile):
        self.stage = self.max_stage
        self.rotation = (self.rotation + 1) % 6
        self.scheduler.sched(self.try_spawn, self.get_delay())
        tile.add(CoverPlant(self.delay, self.sprite_base, self.game, tile.pos, rotation = self.rotation)) # TODO: Is `tile.pos` even a thing?
