import asyncio
import json
import logging
import websockets
import traceback
#import png
#import random
#import math 
#import os

from . import game
from .board import *
from .common import *
from .games import GrowGame, TendGame, PathGame

logging.basicConfig()

async def send_outgoing(queue, socket):
    while True:
        await socket.send(await queue.get())
        queue.task_done()

def mk_msg_dict(msg):
    return {"type":"text", "msg":msg}

class VersionedTile(Tile):
    def __init__(self):
        self.version = -1
        super().__init__()

class Player:
    def __init__(self, lobby, socket, name):
        self.lobby = lobby
        self.outgoing_queue = asyncio.Queue()
        self.outgoing_task = asyncio.create_task(send_outgoing(self.outgoing_queue, socket))
        if not name:
            i=1
            while True:
                name = f"Player {i}"
                for p in lobby.players:
                    if p.name == name:
                        break
                else:
                    self.name = name
                    break
                i += 1
        self.name = name
        lobby.players.append(self)
        self.lobby.broadcast(f">>> {self.name} joined")
        self.status = ""
        self.client_board = Board(tile_offset = None, tile_type = VersionedTile)
        self.board_layout = None
        if self.lobby.game == None:
            self.character = None
        else:
            self.set_char(self.lobby.game.seat_player(self))
    def set_char(self, char):
        self.character = char
        if char != None:
            self.do_frame()
    def send_dict(self, d):
        self.outgoing_queue.put_nowait(json.dumps(d))
    def set_status(self, text):
        if text != self.status:
            self.status = text
            self.send_dict({"type":"status","text":text})
    def whisper_raw(self, msg):
        self.send_dict(mk_msg_dict(msg))
    def say(self, msg):
        self.lobby.broadcast(f"{self.name}: {msg}")
    def rename(self, name):
        self.lobby.broadcast(f">>> {self.name} renamed to {name}")
        self.name = name
    def do_frame(self):
        old_board = self.client_board
        if old_board.min_x == None:
            new_board = Board(tile_offset = None, tile_type = VersionedTile)
        else:
            new_board = Board(
                (old_board.min_x - 1, old_board.min_y - 1), 
                old_board.max_x - old_board.min_x + 2,
                old_board.max_y - old_board.min_y + 2,
                VersionedTile
            )
        send_me = {}
        new_board_layout = self.character.draw_to_board(new_board) # TODO must actually return the layout lololololol
        if new_board_layout != self.board_layout:
            self.board_layout = new_board_layout
            send_me['layout'] = new_board_layout
            # Specifying the layout also clears the board client-side, (TODO this)
            # since usually it doesn't make sense to even use the same
            # sprites if the layout is changing
            old_board = Board(tile_offset = None, tile_type = VersionedTile) # TODO This is used like 3x, make into a fn
        old_bounds = ((old_board.min_x, old_board.min_y), (old_board.max_x, old_board.max_y))
        new_bounds = ((new_board.min_x, new_board.min_y), (new_board.max_x, new_board.max_y))
        if old_board.min_x is None:
            if new_board.min_x is not None:
                old_bounds = new_bounds
        elif new_board.min_x is None:
            new_bounds = old_bounds
        updates = []
        if old_bounds[0][0] is not None:
            for x in range(min(old_bounds[0][0], new_bounds[0][0]), max(old_bounds[1][0], new_bounds[1][0])):
                for y in range(min(old_bounds[0][1], new_bounds[0][1]), max(old_bounds[1][1], new_bounds[1][1])):
                    old_tile = old_board.get_tile((x,y))
                    new_tile = new_board.get_tile((x,y))
                    l1 = len(old_tile.contents)
                    l2 = len(new_tile.contents)
                    if l2 > 0:
                        new_tile.version = old_tile.version
                    i = 0
                    while i < l1 and i < l2:
                        if old_tile.contents[i] != new_tile.contents[i]:
                            break
                        i += 1
                    if l1 == l2 and i == l1:
                        continue # Everything was the same
                    updates.append({"x":x,"y":y,"ver":old_tile.version,"keep":i,"add":new_tile.contents[i:]})
                    if l2 > 0:
                        new_tile.version = int(not new_tile.version)
        if updates or send_me:
            send_me['type'] = 'arena'
            send_me['items'] = updates
            self.send_dict(send_me)
            self.client_board = new_board


class Lobby:
    def __init__(self):
        self.players = []
        self.game = None
    def broadcast_dict(self, d):
        for p in self.players:
            p.send_dict(d)
    def broadcast(self, msg):
        self.broadcast_dict(mk_msg_dict(msg))
    def foo(self):
        self.broadcast_dict({"type":"foo"})
    async def exit_game(self, player):
        if self.game == None:
            raise PebkacException("No game in progress!")

        game = self.game
        self.game = None

        for p in self.players:
            p.character = None
        self.broadcast(f">>> Game was ended by {player.name} (/lobby)")
        # This should never actually suspend, but for safety's sake we remove our avenues
        # of scheduling more tasks before we clean up the old game
        await game.cleanup()
    def start_game(self, player, args):
        if self.game != None:
            raise PebkacException("Game already in progress!")
        self.broadcast(f">>> Game was started by {player.name} (/game)")
        if args == 'tend ':
            self.game = TendGame()
        elif args == 'path ':
            self.game = PathGame()
        else:
            self.game = GrowGame()
        for p in self.players:
            p.set_char(self.game.seat_player(p))
lobby_dict = {}

async def connection_handler(websocket, path):
    message = await websocket.recv()
    if message[:6] != '/name ':
        print(f"First message was not '/name ...', closing socket. Got '{message}'")
        await websocket.close()
        return
    if path not in lobby_dict:
        lobby_dict[path] = Lobby()
    lobby = lobby_dict[path]
    player = Player(lobby, websocket, message[6:])
    # Register player in lobby, make task for sending stuff out on the websocket
    try:
        # websocket.send(str)
        async for message in websocket:
            try:
                if message[:2] == '//':
                    player.say(message[1:])
                elif message[:1] != '/':
                    player.say(message)
                else:
                    if message == '/foo':
                        lobby.foo()
                    elif message[:6] == '/name ':
                        player.rename(message[6:])
                    elif (message + ' ')[:7] == '/lobby ':
                        await lobby.exit_game(player)
                    elif (message + ' ')[:6] == '/game ':
                        lobby.start_game(player, (message+' ')[6:].strip())
                    elif player.character != None:
                        lobby.game.process_command(player.character, message)
                    elif (message + ' ')[:6] == '/help ':
                        # Currently messages are printed in reverse. Maybe fix this?
                        player.whisper_raw('... /name [name] - set your name')
                        player.whisper_raw('... /lobby       - stop the game')
                        player.whisper_raw('... /game        - start a game')
                        player.whisper_raw('... Available server-level commands are:')
                    else:
                        player.whisper_raw('!!! Unknown command (no game in progress)')
            except Exception as e:
                print(f"{player.name} threw:")
                if isinstance(e, PebkacException):
                    print(e)
                else:
                    traceback.print_exc()
                player.whisper_raw(f"!!! Input threw: {e}")
    finally:
        player.outgoing_task.cancel() # Do this first, since it is crucial to prevent resource leaks
        await asyncio.gather(player.outgoing_task, return_exceptions=True)
        lobby.players.remove(player)
        # TODO Need to do something with their character, since it's now orphaned
        # TODO Socket.close(), or something? Want to handle errors here
        lobby.broadcast(f">>> {player.name} has left")

# TODO Port is a program arg
# This code taken from the websockets tutorial, is there any less-ugly way to do this?
loop = asyncio.get_event_loop()
loop.run_until_complete(websockets.serve(connection_handler, port=15000))
loop.run_forever()
