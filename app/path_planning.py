from . import vector as vec

def update_path(start, l, max_len, dest, traversable_fn):
    if len(l) and l[-1][0] == dest:
        # Clicking on the last segment is a special case
        return l[:-1]
    # Indexing between `l` and `ps` will be off by one,
    # but oddly that usually works out correctly for what we want.
    ps = [start] + [x[0] for x in l]
    # Try to get to the dest greedily from each point on the path,
    # starting with where it ends currently
    for i in range(len(ps)-1, -1, -1):
        start_index = i
        pos = ps[i]
        remaining = max_len - i
        steps = []
        # Loop adding more steps until we get there or fail
        while True:
            if pos == dest:
                return l[:start_index] + steps
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
                    if pos in ps:
                        # If it's somewhere we've previously been, jump to there
                        candidate = ps.index(pos)
                        if candidate < start_index:
                            start_index = candidate
                            steps = []
                            remaining = max_len - start_index
                    break
            else:
                # No suitable options found to advance,
                # abandon this starting point
                break
    return l
