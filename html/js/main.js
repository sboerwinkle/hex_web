
let arena = document.getElementById('arena');
let status_area = document.getElementById('status');
let text_area = document.getElementById('text');
let input_area = document.getElementById('input');
text_area.value = ""; // Firefox likes to persist the content on a refresh for some reason

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

function Tile() {
	this.version = -1;
	this.things = [];
}

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

function make_img_tag(x, y, z, src) {
	let tag = document.createElement('img');
	let style = tag.style;
	style.position = 'absolute';
	style.left = (50*x + 25*y) + "px";
	style.top = (43*y) + "px";
	style.zIndex = z;
	tag.src = "assets/" + src + ".png";
	return tag;
}

function update_tile(x, y, version, to_keep, new_items) {
	let tile = get_tile(x, y);
	let things = tile.things;
	if (tile.version != version) alert('Tile out of date at ' + x + ', ' + y + "(local " + tile.version + " vs " + version + ")");
	tile.version = (!version) + 0;
	if (things.length < to_keep) alert('Missing some items at ' + x + ", " + y);
	removed = things.splice(to_keep)
	for (let r of removed) {
		arena.removeChild(r);
	}
	for (let n of new_items) {
		let tag = make_img_tag(x, y, to_keep, n)
		to_keep++;
		things.push(tag);
		arena.appendChild(tag);
	}
	if (things.length == 0) {
		delete board[x][y];
	}
}

function process_message(event) {
	let obj = JSON.parse(event.data);
	if (obj.type == "foo") {
		alert("woah");
	} else if (obj.type == "text") {
		text_area.value = obj.msg + "\n" + text_area.value;
		// text_area.scrollTop = text_area.scrollHeight;
	} else if (obj.type == "arena") {
		for (let item of obj.items) {
			update_tile(item.x, item.y, item.ver, item.keep, item.add);
		}
		// Clean up unused columns. Probably not really necessary?
		colsearch:
		for (let x in board) {
			for (let y in board[x]) {
				continue colsearch;
			}
			delete board[x]
		}
	} else if (obj.type == "status") {
		status_area.textContent = obj.text;
	} else {
		alert("Unknown message type '" + obj.type + "'");
	}
}

function handle_close(event) {
	alert("Either the server shut down, or there's a bug maybe!");
}

let ws = new WebSocket(`ws://${window.location.hostname}:15000`);
ws.onmessage = process_message;
ws.onclose = handle_close;

document.getElementById('form').onsubmit = function () {
	ws.send(input_area.value);
	input_area.value = "";
	return false; // Do not reload page
}

arena.onclick = function(evt) {
	let offset = getOffset(evt);
	let tile_y = Math.floor((offset.y - 7) / 43);
	let tile_x = Math.floor((offset.x - 25*tile_y) / 50);
	ws.send(`/click ${tile_x} ${tile_y}`);
}
