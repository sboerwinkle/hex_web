
let arena = document.getElementById('arena');
let context = arena.getContext('2d');
let status_area = document.getElementById('status');
let text_area = document.getElementById('text');
let input_area = document.getElementById('input');
text_area.value = ""; // Firefox likes to persist the content on a refresh for some reason

// Circular buffer
let history = [];
let selectedHistoryIx = 0;
let historyIx = 0;
const historySize = 50;

// This function modified from this stackoverflow answer: https://stackoverflow.com/a/10816667
/*
function getOffset(evt) {
  var el = evt.target,
      x = evt.pageX,
      y = evt.pageY;

  while (el && !isNaN(el.offsetLeft) && !isNaN(el.offsetTop)) {
    x -= el.offsetLeft;
    y -= el.offsetTop;
    el = el.offsetParent;
  }

  return { x: x, y: y };
}
*/
function getOffset(evt) {
	return { x: evt.pageX - arena.offsetLeft + arena.scrollLeft, y: evt.pageY - arena.offsetTop + arena.scrollTop };
}
// TODO: Cannot scroll to items offscreen to the top or left. If this is needed, we'd have to detect that case and shift everything.


let board = {};
// Control the translation from board coords to screen coords.
// Defaults here correspond to a hex grid, but are largely irrelevant since the first
// message should include "layout" which will overwrite them
let x_step = 50; // Distance sideways to next tile
let y_step = 43; // Distance vertically to next row
let row_shift = 25; // How much each subsequent row is shifted, e.g. x_step/2 for a hex grid
let y_offset = 7; // How far down the sprite the button "visually" starts; this applies to hex grids since the image encompasses the whole hex, but the clickable area is a rectangle (and as such isn't the entire vertical height)
let clearImageName = 'hex_empty';

// Just a valid target for drawing, even if it has no content
const failImage = new Image();
let firstFailure = true;

let images = {};
const promises = {};
function requireImage(name) {
	if (!images[name] && !promises[name]) {
		const image = new Image();
		promises[name] = new Promise((resolve, _) => {
			image.addEventListener('load', () => {
				//setTimeout(() => { // For testing, imitates slow load
				delete promises[name];
				images[name] = image;
				resolve();
				//}, 2000);          // See above
			});
			image.addEventListener('error', e => {
				if (firstFailure) {
					firstFailure = false;
					alert("An image failed to load. Further failures will only show in the console.");
				}
				console.log("Error while loading " + image.src);
				delete promises[name];
				images[name] = failImage;
				resolve();
			});
		});
		// It seems like maybe this is *immediately* loading the image some times,
		// so it cannot happen inside the promise or it will try to delete its entry in `promises`
		// before the promise is fully created and assigned.
		image.src = "assets/" + name + ".png";
	}
}

function Tile() {
	this.version = -1;
	this.things = [];
	this.pendingDraws = [];
}

async function addDraws(tile, x, y, items, reset = false) {
	let xPixels = x_step*x + row_shift*y;
	let yPixels = y_step*y;
	for (let i of items) requireImage(i);
	let l = tile.pendingDraws;
	if (l.length) {
		// There is an existing thread for this tile
		if (reset) {
			// Other thread will immediately exit when it resumes execution.
			// Note that we're playing very carefully with object references here,
			// as the identity of `tile.pendingDraws` is about to change.
			l.splice(0);
		} else {
			// There's an existing thread,
			// and we're only adding to its tasks,
			// so we can just dump it onto the list and move on.
			l.push(...items);
			return;
		}
	}

	// Shallow copy; probably unnecessary, but removes any subtle "gotchas" about what values you can pass for `items`.
	l = items.slice();
	tile.pendingDraws = l;

	while (l.length) {
		let name = l[0];
		let image;
		if (images[name]) {
			image = images[name];
		} else {
			if (!promises[name]) {
				console.log("No image or promise for " + name);
				image = failImage;
			} else {
				await promises[name];
				continue;
			}
		}
		context.drawImage(image, xPixels, yPixels);
		l.shift();
	}
}

// All this just-in-time row and tile creation was from back when we thought it might scroll more.
// Nowadays we could maybe do all this up front?
function get_tile(x, y) {
	let col = board[x];
	if (col === undefined) {
		col = {};
		board[x] = col;
	}
	let tile = col[y];
	if (tile === undefined) {
		tile = new Tile();
		col[y] = tile;
	}
	return tile;
}

function make_button_tag(text, listener) {
	let tag = document.createElement('button');
	tag.type = 'button';
	tag.textContent = text;
	tag.addEventListener('click', listener);
	return tag;
}

function make_span_tag(text) {
	let tag = document.createElement('span');
	tag.textContent = text;
	return tag;
}

function reset_board() {
	for (let x in board) {
		let col = board[x];
		for (let y in col) {
			let tile = col[y];
			// Make sure any drawing threads will immediately exit when they resume
			tile.pendingDraws.splice(0);
		}
	}
	context.clearRect(0, 0, arena.width, arena.height);
	// Spares us having to `delete` each tile and col individually
	board = {};
	// Not sure if this part is necessary, but nothing wrong with cleaning up the images I guess
	images = {};
}

function update_tile(x, y, version, to_keep, new_items) {
	let tile = get_tile(x, y);
	let things = tile.things;
	if (tile.version != version) alert('Tile out of date at ' + x + ', ' + y + "(local " + tile.version + " vs " + version + ")");
	tile.version = (!version) + 0;

	if (things.length < to_keep) alert('Missing some items at ' + x + ", " + y);
	let trimmed = things.length > to_keep;
	things.splice(to_keep);
	things.push(...new_items);

	if (trimmed) {
		// Have to redraw from scratch in this case
		let items = [clearImageName].concat(things);
		addDraws(tile, x, y, items, true);
	} else {
		// Fine to just draw more stuff, the simple way
		addDraws(tile, x, y, new_items);
	}
	// This could probably go away if we were allocating all tiles in advance, not sure though
	if (things.length == 0) tile.version = -1;
}

function set_status(input) {
	let start_index = 0;
	let bits = [];
	while (true) {
		let index = input.indexOf('{', start_index);
		if (index == -1) {
			if (start_index < input.length) {
				bits.push(input.substring(start_index));
			}
			break;
		}
		if (index > start_index) bits.push(input.substring(start_index, index));
		let index2 = input.indexOf('}', index) + 1;
		if (index2 == 0) {
			console.log("Unterminated '{' in:");
			console.log(input);
			break;
		}
		bits.push(input.substring(index, index2));
		start_index = index2;
	}
	let newChildren = bits.map(bit => {
		if (bit[0] == '{') {
			bit = bit.substring(1, bit.length - 1);
			let split = bit.indexOf('|');
			let text;
			let listener;
			if (split == -1) {
				text = bit;
				listener = () => { alert('broken'); };
			} else {
				text = bit.substring(0, split);
				let action = bit.substring(split + 1);
				listener = () => { ws.send(action); };
			}
			return make_button_tag(text, listener);
		} else {
			return make_span_tag(bit);
		}
	});
	status_area.replaceChildren(...newChildren);
}

function process_message(event) {
	let obj = JSON.parse(event.data);
	if (obj.type == "foo") {
		alert("woah");
	} else if (obj.type == "text") {
		// MDN has some caveat where scrollTop might not be an integer in some cases.
		// I've never run into an issue with this, but I'd rather just be extra careful.
		const scrolling = Math.abs(text_area.scrollTop + text_area.clientHeight - text_area.scrollHeight) < 1;
		text_area.value = text_area.value + "\n" + obj.msg;
		if (scrolling) text_area.scrollTop = text_area.scrollHeight; // Clamps to maximum sensible value
	} else if (obj.type == "arena") {
		//text_area.value = "ping\n" + text_area.value;
		if (obj.layout) {
			reset_board();
			let layout = obj.layout
			x_step = layout[0];
			y_step = layout[1];
			row_shift = layout[2];
			y_offset = layout[3];
			clearImageName = layout[4];
		}
		for (let item of obj.items) {
			update_tile(item.x, item.y, item.ver, item.keep, item.add);
		}
	} else if (obj.type == "status") {
		set_status(obj.text);
	} else {
		alert("Unknown message type '" + obj.type + "'");
	}
}

function handle_close(event) {
	alert("Lost connection to server");
}

let ws = new WebSocket(`ws://${window.location.hostname}:15000`);
ws.onmessage = process_message;
ws.onclose = handle_close;
ws.onopen = () => { ws.send("/name " + (localStorage.name || "")); }

document.getElementById('form').onsubmit = function () {
	const msg = input_area.value;
	input_area.value = "";
	if (msg.startsWith("/name ")) localStorage.name = msg.substring(6)
	ws.send(msg);
	if (msg != history[(historyIx + historySize - 1) % historySize]) {
		history[historyIx] = msg;
		historyIx = (historyIx + 1) % historySize;
	}
	selectedHistoryIx = historyIx;
	return false; // Do not reload page
}

arena.onclick = function(evt) {
	let offset = getOffset(evt);
	let tile_y = Math.floor((offset.y - y_offset) / y_step);
	let tile_x = Math.floor((offset.x - row_shift*tile_y) / x_step);
	ws.send(`/click ${tile_x} ${tile_y}`);
}

input_area.onkeydown = function(evt) {
	if (evt.keyCode == 38) { // up arrow
		evt.preventDefault();
		let newIx = (selectedHistoryIx + historySize - 1) % historySize;
		// No wrapping, no undefined entries
		if (newIx == historyIx || history[newIx] == undefined) return;

		selectedHistoryIx = newIx;
		input_area.value = history[selectedHistoryIx];
	} else if (evt.keyCode == 40) { // down arrow
		evt.preventDefault();
		// Prevent wrapping the circular buffer
		if (selectedHistoryIx == historyIx) return;

		selectedHistoryIx = (selectedHistoryIx + 1) % historySize;
		if (selectedHistoryIx == historyIx) {
			input_area.value = "";
		} else {
			input_area.value = history[selectedHistoryIx];
		}
	}
}

/*
function arena_to_bottom() { to_bottom(arena.parentElement); }
function text_to_bottom() { to_bottom(text_area.parentElement); }
function to_bottom(el) {
	el.remove();
	content.appendChild(el);
}
*/
