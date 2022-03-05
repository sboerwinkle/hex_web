from . import vector as vec

def update_path(start, l, max_len, dest, traversable_fn):
    # This ordering is better for when we care about the destination, and less about the path.
    ps = [(start, 0)] + [(l[i][0], i+1) for i in range(len(l))]
    # If we care about the path more, we would add something like this:
    #ps.reverse()
    #if len(l) and ps[0][0] == dest:
    #    ps = ps[1:]

    # Try to get to the dest greedily from each of our possible starting points
    for pos, i in ps:
        remaining = max_len - i
        # This is just an efficiency boost when searching forwards,
        # and if searching backwards it allows us to enforce finding
        # a new path under some conditions.
        do_check = i < len(l)
        steps = []
        # Loop adding more steps until we get there or fail
        while True:
            if pos == dest:
                return l[:i] + steps
            offset = vec.sub(dest, pos)
            if vec.measure(offset) > remaining:
                # Won't be able to complete our path in time,
                # abandon this starting point
                break
            for option in vec.calc_angles(offset, 1):
                next = vec.add(pos, vec.units[option])
                if traversable_fn(next):
                    remaining -= 1
                    pos = next
                    steps.append((pos, option))
                    break
            else:
                # No suitable options found to advance,
                # abandon this starting point
                break
            if do_check:
                do_check = False
                if l[i][0] == pos:
                    # In this case we just re-planned the same next step,
                    # which we can throw out as irrelevant calculation.
                    break
    return l
