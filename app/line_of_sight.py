from . import vector as vec
from heapq import heappush, heappop

# All these calculations are done in hex grid coordinate space,
# which is slightly skewed and stretched from actual "display" space.
# (The one exception is we priority queue our spaces based on the display distance,
#  because I can't picture the grid coord space clearly enough to be sure it works there too)
# This works because affine transformations preserve straight lines,
# so if you can see it in one space you can see it in the other.

# Other assumptions:
# - Shadows-making obstacles always fill the entire hex.
#     This ensures no hex is visible from two different arcs at once.

# Let the cell-to-cell distance (between centers) be 1 unit. Assume this is a propery rendered hex grid;
#   we will be transforming it into a square grid and tracking the locations of the corners as we go.
#   The vertical row-to-row distance is sqrt(3)/2, or 1.5/sqrt(3).
#   Each edge of a hex cell, and the center-to-vertex distance, is 1/sqrt(3).
# Start by stretching the grid vertically so the row-to-row distance is 1;
#   the distance from a cell's center to its top or bottom vertex is now exactly 2/3.
#   deltas = [(0.5, 1/3), (0, 2/3), (-0.5, 1/3), (-0.5, -1/3), (0, -2/3), (0.5, -1/3)]
# Now we just need to shear the grid a bit to square it up;
#   each point's X loses 1/2 of its Y.
#   deltas = [(1/3, 1/3), (-1/3, 2/3), (-2/3, 1/3), (-1/3, -1/3), (1/3, -2/3), (2/3, -1/3)]
# Whups! Floating point math is for scrubs, so we scale everything up by 3x.
corner_deltas = [(1, 1), (-1, 2), (-2, 1), (-1, -1), (1, -2), (2, -1)]

def get_visual_extent(v):
    v = vec.mult(v, 3)
    leftmost = rightmost = vec.add(v, corner_deltas[0])
    for i in range(1, 6):
        test = vec.add(v, corner_deltas[i])
        if vec.cross(test, leftmost) > 0:
            leftmost = test
        elif vec.cross(test, rightmost) < 0:
            rightmost = test
    if vec.cross(leftmost, rightmost) <= 0:
        raise Exception("visual extent of a cell should always be less that half a circle!")
    return (leftmost, rightmost)

# Visual arc, a range not obscured by shadow
class Arc:
    def __init__(self, heap, marked):
        self.heap = heap
        self.marked = marked

class WholeArc(Arc):
    def intersects(self, pair):
        return True
    def __repr__(self):
        return "WholeArc"
    def contains(self, v):
        return True
    def shadow(self, pair):
        return [ConcaveArc(pair[1], pair[0], self.heap, self.marked)]

class ConcaveArc(Arc):
    def __init__(self, left, right, *a, **ka):
        super().__init__(*a, **ka)
        self.left = left
        self.right = right
    def __repr__(self):
        return f"ConcaveArc between {self.left} and {self.right}"
    def intersects(self, pair):
        return (
            vec.cross(pair[0], self.right) > 0 or
            vec.cross(self.left, pair[0]) > 0 or
            vec.cross(self.left, pair[1]) > 0
        )
    def contains(self, v):
        return vec.cross(self.left, v) >= 0 or vec.cross(v, self.right) >= 0
    def shadow(self, pair):
        if vec.cross(pair[1], self.right) > 0:
            # Pass ownership of our heap/marked to this Arc, it may be the only one
            right_arc = ConvexArc(pair[1], self.right, self.heap, self.marked)
            if vec.cross(pair[0], self.left) >= 0:
                if vec.cross(self.right, pair[0]) >= 0:
                    return [right_arc]
                else:
                    self.right = pair[0]
                    self.heap = self.heap.copy()
                    self.marked = self.marked.copy()
                    return [self, right_arc]
            else:
                left_arc = ConvexArc(self.left, pair[0], self.heap.copy(), self.marked.copy())
                return [left_arc, right_arc]
        else:
            if vec.cross(pair[1], self.left) >= 0:
                if vec.cross(self.left, pair[0]) > 0:
                    return [ConvexArc(self.left, pair[0], self.heap, self.marked)]
                else:
                    self.right = pair[0]
                    return [self]
            else:
                if vec.cross(pair[0], self.left) >= 0:
                    self.left = pair[1]
                    return [self]
                else:
                    left_arc = ConvexArc(self.left, pair[0], self.heap.copy(), self.marked.copy())
                    self.left = pair[1]
                    return [left_arc, self]

class ConvexArc(Arc):
    def __init__(self, left, right, *a, **ka):
        super().__init__(*a, **ka)
        self.left = left
        self.right = right
    def __repr__(self):
        return f"ConvexArc between {self.left} and {self.right}"
    def intersects(self, pair):
        if vec.cross(self.left, pair[0]) > 0:
            return vec.cross(pair[0], self.right) > 0
        else:
            return vec.cross(self.left, pair[1]) > 0
    def contains(self, v):
        return vec.cross(self.left, v) >= 0 and vec.cross(v, self.right) >= 0
    def shadow(self, pair):
        if vec.cross(pair[0], self.left) >= 0:
            if vec.cross(self.right, pair[1]) >= 0:
                return []
            else:
                self.left = pair[1]
                return [self]
        else:
            if vec.cross(self.right, pair[1]) >= 0:
                self.right = pair[0]
                return [self]
            else:
                other = ConvexArc(pair[1], self.right, self.heap.copy(), self.marked.copy())
                self.right = pair[0]
                return [self, other]

def los_fill(occlude_func, src):
    ret = []
    ret.append((src, 3))
    start_heap = []
    for u in vec.units:
        heappush(start_heap, (1, u))
    start_marked = set(vec.units)
    start_marked.add((0, 0))
    arcs = [WholeArc(start_heap, start_marked)]
    while len(arcs) > 0:
        arc = arcs[0]
        while True:
            (distance, offset) = heappop(arc.heap)
            #if distance < 1.5:
            #    print('Pulled ' + str(offset))

            pair = get_visual_extent(offset)
            if not arc.intersects(pair):
                continue
            position = vec.add(src, offset)
            if occlude_func(position):
                ret.append((position, 3))
                arcs = arc.shadow(pair) + arcs[1:]
                #if distance < 1.5:
                #    print('arcs is now ' + repr(arcs))
                break

            """
            # Will include the position w/ `True` if the center is visible,
            # or `False` if part of the cell (but not the center) is visible.
            if not arc.contains(offset):
                visibility = 1
            elif arc.contains(pair[0]) and arc.contains(pair[1]):
                visibility = 3
            else:
                visibility = 2
            """
            # Experimenting with: hex is fully colored if you can fully see a 1/3 scale hex in the center,
            # and is dim otherwise
            inner_pair = get_visual_extent(vec.mult(offset, 3))
            # For our situation, containing both ends is equivalent to encompassing the entire arc
            if arc.contains(inner_pair[0]) and arc.contains(inner_pair[1]):
                visibility = 3
            else:
                visibility = 1

            ret.append((position, visibility))

            for u in vec.units:
                neighbor = vec.add(offset, u)
                if neighbor not in arc.marked:
                    arc.marked.add(neighbor)
                    heappush(arc.heap, (vec.display_dist(neighbor), neighbor))
    return ret
