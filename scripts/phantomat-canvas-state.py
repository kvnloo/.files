#!/usr/bin/env python3
"""Snapshot and restore the native layout of the environment's Hyprland instance."""
import contextlib
import copy
import fcntl
import json
import os
from pathlib import Path
import re
import shlex
import signal
import subprocess
import sys
import tempfile
import time


def report(message):
    print(f'phantomat-toggle: {message}', file=sys.stderr)


def notify(message):
    """Nobody reads stderr of a key binding; a failed press must not look like a dead key."""
    instance = os.environ.get('HYPRLAND_INSTANCE_SIGNATURE')
    if not instance or os.environ.get('PHANTOMAT_DRY_RUN') == '1':
        return
    with contextlib.suppress(OSError, subprocess.SubprocessError):
        subprocess.run(['hyprctl', '-i', instance, 'notify', '0', '7000', '0',
                        'phantomat-toggle: '+message[:240]], capture_output=True, timeout=3)


def safe_name(value):
    if not isinstance(value, str) or not value or any(c in value for c in ',;\r\n'):
        raise ValueError(f'unsafe workspace/monitor name: {value!r}')
    return value


def workspace_arg(ws):
    name = safe_name(ws['name'])
    return name if name.startswith('special:') or name == str(ws['id']) else 'name:' + name


def validate_clients(clients):
    if not isinstance(clients, list):
        raise ValueError('clients must be an array')
    seen = set()
    for c in clients:
        address = c['address']
        if not re.fullmatch(r'0x[0-9a-fA-F]+', address) or address in seen:
            raise ValueError('invalid or duplicate client address')
        seen.add(address)
        workspace_arg(c['workspace'])
        for field in ('floating', 'pinned'):
            if type(c[field]) is not bool:
                raise ValueError(f'invalid {field} for {address}')
        for field in ('at', 'size'):
            if len(c[field]) != 2 or any(type(v) not in (int, float) for v in c[field]):
                raise ValueError(f'invalid {field} for {address}')
        if min(c['size']) <= 0:
            raise ValueError(f'invalid size for {address}')
        for field in ('fullscreen', 'fullscreenClient'):
            if type(c.get(field, c['fullscreen'])) is not int or not 0 <= c.get(field, c['fullscreen']) <= 3:
                raise ValueError(f'invalid {field} for {address}')
        if not isinstance(c['grouped'], list) or any(not re.fullmatch(r'0x[0-9a-fA-F]+', a) for a in c['grouped']):
            raise ValueError(f'invalid group for {address}')


def same_window(saved, current):
    return (saved['address'] == current['address'] and current.get('mapped', True)
            and all(saved.get(k) is None or saved[k] == current.get(k) for k in ('pid', 'stableId')))


def bounds(boxes):
    x, y = min(b[0] for b in boxes), min(b[1] for b in boxes)
    return [x, y, max(b[0]+b[2] for b in boxes)-x, max(b[1]+b[3] for b in boxes)-y]


def leaves(node):
    if not node:
        return []
    if 'members' in node:
        return [node]
    return leaves(node['children'][0]) + leaves(node['children'][1])


def derive_tree(tiles):
    if not tiles:
        return None
    if len(tiles) == 1:
        return tiles[0]
    for split, axis in (('h', 0), ('v', 1)):
        ordered = sorted(tiles, key=lambda t: (t['box'][axis], t['representative']))
        end = ordered[0]['box'][axis] + ordered[0]['box'][axis+2]
        for i, tile in enumerate(ordered[1:], 1):
            if tile['box'][axis] >= end:
                children = [derive_tree(ordered[:i]), derive_tree(ordered[i:])]
                return dict(split=split, box=bounds([t['box'] for t in tiles]), children=children)
            end = max(end, tile['box'][axis]+tile['box'][axis+2])
    raise ValueError('overlapping tiles cannot be recovered as a dwindle tree')


def monitor_size(monitor):
    width, height = monitor['width'], monitor['height']
    if monitor.get('transform', 0) % 2:
        width, height = height, width
    scale = monitor.get('scale', 1)
    return round(width/scale), round(height/scale)


def monitor_content(monitor, metrics):
    width, height = monitor_size(monitor)
    left, top, right, bottom = monitor.get('reserved', [0]*4)
    gt, gr, gb, gl = metrics['gaps_out']
    border = metrics['border']
    return [monitor['x']+left+gl+border, monitor['y']+top+gt+border,
            width-left-right-gl-gr-2*border, height-top-bottom-gt-gb-2*border]


# Mapped windows on any monitor's active or nonzero special workspace, plus pinned
# windows, keep their snapshot box. For each monitor in id order, hidden normal
# workspaces in ascending workspace-id order get separate full logical-monitor
# blocks. Hidden special workspaces share one further block per monitor. The
# logical size swaps raw width/height for odd transforms, then rounds each / scale.
# The owning monitor comes from the client, falling back to workspace monitor data.
# From its centre, point away from the centroid of all OTHER monitor centres:
# choose the axis with larger absolute delta (ties use x), and its delta's sign
# (zero uses +); one monitor uses +x. Block k starts at monitor origin plus
# direction * k * (logical extent on that axis + round(0.10 * logical width)),
# starting at k=1 and skipping k until it intersects neither any logical monitor
# box nor an earlier block. Translate each saved box by block origin minus its
# monitor origin. Missing/degenerate hidden boxes and unmapped windows are omitted.
# Fullscreen/maximised windows become plain floating windows with the box they
# occupied; grouped members keep their own saved box too.
def canvas_targets(saved):
    monitors = sorted(saved['monitors'], key=lambda m: m['id'])
    boxes = {m['id']: [int(m['x']), int(m['y']), *monitor_size(m)] for m in monitors}
    visible = {m['activeWorkspace']['id'] for m in monitors}
    visible.update(m['specialWorkspace']['id'] for m in monitors
                   if m.get('specialWorkspace', {}).get('id', 0))
    workspaces = {ws['id']: ws for ws in saved.get('workspaces', [])}
    targets, hidden = {}, {}
    for window in saved['clients']:
        if not window.get('mapped', True):
            continue
        ws = window['workspace']
        is_visible = window.get('pinned', False) or ws['id'] in visible
        if not is_visible and (len(window.get('at', [])) != 2
                               or len(window.get('size', [])) != 2
                               or min(window['size']) <= 0):
            continue
        rect = [int(v) for v in window['at']+window['size']]
        if is_visible:
            targets[window['address']] = rect
            continue
        owner = window.get('monitor')
        monitor = next((m for m in monitors if owner in (m['id'], m['name'])), None)
        if monitor is None:
            owner = ws.get('monitor', workspaces.get(ws['id'], {}).get('monitor'))
            monitor = next((m for m in monitors if owner in (m['id'], m['name'])), None)
        if monitor is None:
            continue
        normal, special = hidden.setdefault(monitor['id'], ({}, []))
        if ws['name'].startswith('special:'):
            special.append((window['address'], rect))
        else:
            normal.setdefault(ws['id'], []).append((window['address'], rect))

    occupied = list(boxes.values())
    for monitor in monitors:
        x, y, width, height = boxes[monitor['id']]
        others = [box for mid, box in boxes.items() if mid != monitor['id']]
        dx, dy = 1, 0
        if others:
            dx = x+width/2 - sum(b[0]+b[2]/2 for b in others)/len(others)
            dy = y+height/2 - sum(b[1]+b[3]/2 for b in others)/len(others)
        axis = 0 if abs(dx) >= abs(dy) else 1
        sign = 1 if (dx, dy)[axis] >= 0 else -1
        step = (width, height)[axis] + round(.10*width)
        normal, special = hidden.get(monitor['id'], ({}, []))
        blocks = [normal[ws] for ws in sorted(normal)] + ([special] if special else [])
        k = 0
        for windows in blocks:
            while True:
                k += 1
                block = [x, y, width, height]
                block[axis] += sign*k*step
                if not any(block[0] < b[0]+b[2] and b[0] < block[0]+block[2]
                           and block[1] < b[1]+b[3] and b[1] < block[1]+block[3]
                           for b in occupied):
                    break
            occupied.append(block)
            for address, rect in windows:
                targets[address] = [rect[0]+block[0]-x, rect[1]+block[1]-y, *rect[2:]]
    return targets


def fullscreen_hole(root, peers, metrics):
    """Undo inner gutters, subtract peer cells, then inset the one rectangular hole."""
    x, y, w, h = root
    right, bottom = x+w, y+h
    gt, gr, gb, gl = metrics['gaps_in']
    border = metrics['border']
    expanded = []
    for box in peers:
        a, b, cw, ch = box
        expanded.append([x if a == x else a-gl-border,
                         y if b == y else b-gt-border,
                         right if a+cw == right else a+cw+gr+border,
                         bottom if b+ch == bottom else b+ch+gb+border])
    xs = sorted({x, right} | {v for b in expanded for v in (b[0], b[2]) if x < v < right})
    ys = sorted({y, bottom} | {v for b in expanded for v in (b[1], b[3]) if y < v < bottom})
    holes = [[a, b, c-a, d-b] for a, c in zip(xs, xs[1:]) for b, d in zip(ys, ys[1:])
             if not any(p <= (a+c)/2 < r and q <= (b+d)/2 < s for p, q, r, s in expanded)]
    if not holes:
        raise ValueError('fullscreen tile has no recoverable hole')
    hole = bounds(holes)
    if sum(b[2]*b[3] for b in holes) != hole[2]*hole[3]:
        raise ValueError('fullscreen hole is not rectangular; layout metrics may differ')
    a, b, cw, ch = hole
    l, t = (gl+border if a != x else 0), (gt+border if b != y else 0)
    r, s = (gr+border if a+cw != right else 0), (gb+border if b+ch != bottom else 0)
    result = [a+l, b+t, cw-l-r, ch-t-s]
    if min(result[2:]) <= 0:
        raise ValueError('fullscreen hole has no positive content area')
    return result


def workspace_trees(clients, monitors, metrics):
    indexed = {c['address']: c for c in clients if c.get('mapped', True)}
    by_monitor = {m['id']: m for m in monitors}
    workspaces = {}
    seen = set()
    for c in indexed.values():
        if c['floating']:
            continue
        members = [a for a in c['grouped'] if a in indexed] or [c['address']]
        key = tuple(members)
        if key in seen:
            continue
        seen.add(key)
        visible = next((indexed[a] for a in members if not indexed[a].get('hidden', False)), c)
        header = metrics.get('groupbar', 0) if c['grouped'] else 0
        if header and metrics.get('groupbar_stacked'):
            header = metrics['groupbar_member']*len(members)+metrics['groupbar_upper']
        rect = visible['at'] + visible['size']
        box = [rect[0], rect[1]-header, rect[2], rect[3]+header]
        tile = dict(members=members, representative=visible['address'], rect=rect,
                    box=box, header=header, fullscreen=visible['fullscreen'], monitor=c['monitor'])
        workspaces.setdefault(str(c['workspace']['id']), []).append(tile)
    for tiles in workspaces.values():
        full = [t for t in tiles if t['fullscreen']]
        if len(full) > 1:
            raise ValueError('multiple fullscreen tiles obscure the native tree')
        if full:
            tile = full[0]
            monitor = by_monitor.get(tile['monitor'])
            if monitor is None:
                raise ValueError('fullscreen tile monitor is unavailable')
            tile['box'] = fullscreen_hole(monitor_content(monitor, metrics),
                                          [t['box'] for t in tiles if t is not tile], metrics)
            a, b, w, h = tile['box']
            tile['rect'] = [a, b+tile['header'], w, h-tile['header']]
    return {ws: derive_tree(tiles) for ws, tiles in workspaces.items()}


def prune_tree(node, survivors):
    if not node:
        return None
    if 'members' in node:
        members = [a for a in node['members'] if a in survivors]
        if not members:
            return None
        rep = node['representative'] if node['representative'] in members else members[0]
        return dict(node, members=members, representative=rep)
    children = [prune_tree(n, survivors) for n in node['children']]
    if not all(children):
        return children[0] or children[1]
    return dict(node, children=children)


def resize_command(address, width, height):
    return ('resizewindowpixel', f'exact {int(width)} {int(height)},address:{address}')


def cursor_command(box):
    x, y, width, height = box
    return ('movecursor', f'{int(x+width/2)} {int(y+height/2)}')


def rebuild_plan(tree):
    tiles = leaves(tree)
    if not tiles:
        return []
    commands = [('setfloating', 'address:'+t['representative']) for t in tiles]
    commands.append(cursor_command(tree['box']))
    commands.append(('focuswindow', 'address:'+tiles[0]['representative']))
    commands.append(('settiled', 'address:'+tiles[0]['representative']))

    def insert(node):
        if 'members' in node:
            return
        first, second = node['children']
        rep = leaves(first)[0]
        # The first representative still occupies this whole node until insertion.
        commands.extend([cursor_command(node['box']),
                         ('focuswindow', 'address:'+rep['representative']),
                         ('layoutmsg', 'preselect '+('r' if node['split'] == 'h' else 'd')),
                         ('settiled', 'address:'+leaves(second)[0]['representative']),
                         resize_command(rep['representative'], first['box'][2], first['box'][3]-rep['header'])])
        insert(first)
        insert(second)
    insert(tree)
    return commands


def tile_differences(tree, current):
    indexed = {c['address']: c for c in current}
    differences = []
    for tile in leaves(tree):
        for address in tile['members']:
            c = indexed.get(address)
            if c is not None and (c['floating'] or c['at']+c['size'] != tile['rect']):
                differences.append(f'{address} tile {c["at"]+c["size"]} != {tile["rect"]}, floating={c["floating"]}')
    return differences


class Hyprctl:
    def __init__(self, instance, dry=False):
        self.instance, self.dry = instance, dry

    def run(self, *args, mutation=False, timeout=8):
        argv = ['hyprctl', '-i', self.instance, *args]
        if self.dry:
            print(shlex.join(argv), file=sys.stdout if mutation else sys.stderr)
            if mutation:
                return 'ok'
        result = subprocess.run(argv, text=True, capture_output=True, timeout=timeout)
        if result.returncode:
            raise RuntimeError(f'{shlex.join(argv)}: {result.stderr.strip()} {result.stdout.strip()}')
        output = result.stdout.strip()
        if mutation and any(line.strip() != 'ok' for line in output.splitlines() if line.strip()):
            raise RuntimeError(f'{shlex.join(argv)}: {output}')
        if mutation and not output:
            raise RuntimeError(f'{shlex.join(argv)}: empty dispatcher response')
        return output

    def query(self, name, *args, timeout=8):
        return json.loads(self.run('-j', name, *args, timeout=timeout))

    def batch(self, commands):
        if commands:
            items = ['keyword '+arg if name == 'keyword' else 'dispatch '+name+' '+arg
                     for name, arg in commands]
            # Linux limits each argv string to 32 pages, independently of ARG_MAX.
            limit = min(32*os.sysconf('SC_PAGE_SIZE')-1, os.sysconf('SC_ARG_MAX')//2)
            chunks, pending, size = [], [], 0
            for item in items:
                length = len(item.encode())
                if length > limit:
                    raise ValueError('one hyprctl batch command exceeds the argv limit')
                if pending and size+2+length > limit:
                    chunks.append('; '.join(pending))
                    pending, size = [], 0
                size += length+(2 if pending else 0)
                pending.append(item)
            chunks.append('; '.join(pending))
            if len(chunks) > 1:
                report(f'hyprctl argument limit requires {len(chunks)} batch calls')
            for chunk in chunks:
                self.run('--batch', chunk, mutation=True)

    def keyword(self, name, value):
        self.run('keyword', name, str(value), mutation=True)


@contextlib.contextmanager
def temporary_options(hc, wanted, journal=None):
    previous = {}
    if journal and not hc.dry:
        # An interrupted restore left the user's own values here; the live ones are ours.
        try:
            previous = {k: int(v) for k, v in json.loads(journal.read_text()).items() if k in wanted}
        except (OSError, ValueError, TypeError, AttributeError):
            previous = {}
    try:
        current = {name: hc.query('getoption', name)['int'] for name in wanted}
        for name, value in wanted.items():
            if current[name] != value:
                previous.setdefault(name, current[name])
        if journal and not hc.dry:
            save_atomic(journal, previous)
        hc.batch([('keyword', name+' '+str(value)) for name, value in wanted.items()
                  if current[name] != value])
        yield
    finally:
        errors = []
        for name, old in reversed(list(previous.items())):
            try:
                hc.keyword(name, old)
            except Exception as error:
                errors.append(str(error))
        if errors:
            raise RuntimeError('could not restore temporary options: '+'; '.join(errors))


@contextlib.contextmanager
def preserve_cursor(hc):
    position = None
    try:
        cursor = hc.query('cursorpos')
        position = ('movecursor', f'{int(cursor["x"])} {int(cursor["y"])}')
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.SubprocessError) as error:
        report(f'could not save cursor position: {error}')
    restored = False

    def restore(collect=None, completed=False):
        nonlocal restored
        if collect is not None:
            if position:
                collect.append(position)
            return position
        if completed:
            restored = True
            return
        if restored:
            return
        restored = True
        if position:
            try:
                hc.batch([position])
            except (OSError, RuntimeError, subprocess.SubprocessError) as error:
                report(f'could not restore cursor position: {error}')
    try:
        yield restore
    finally:
        restore()


def capture_metrics(hc):
    def integer(name):
        return hc.query('getoption', name)['int']

    def gaps(name):
        data = hc.query('getoption', name)
        value = data.get('custom', str(data.get('int', '')))
        values = [int(v) for v in re.findall(r'-?\d+', value)]
        if not 1 <= len(values) <= 4:
            raise ValueError(f'cannot parse {name}: {data}')
        return (values*4 if len(values) == 1 else values*2 if len(values) == 2
                else [*values, values[1]] if len(values) == 3 else values)
    upper = integer('group:groupbar:gaps_out')*integer('group:groupbar:keep_upper_gap')
    member = (integer('group:groupbar:gaps_out')+integer('group:groupbar:indicator_height')
              +integer('group:groupbar:indicator_gap'))
    if integer('group:groupbar:gradients') or integer('group:groupbar:render_titles'):
        member += integer('group:groupbar:height')
    return dict(gaps_out=gaps('general:gaps_out'), gaps_in=gaps('general:gaps_in'),
                border=integer('general:border_size'),
                groupbar=(member+upper if integer('group:groupbar:enabled') else 0),
                groupbar_stacked=integer('group:groupbar:stacked'),
                groupbar_member=member, groupbar_upper=upper)


def snapshot(hc):
    clients = hc.query('clients')
    validate_clients(clients)
    monitors = hc.query('monitors')
    metrics = capture_metrics(hc)
    try:
        cursor = hc.query('cursorpos')
        cursor = [int(cursor['x']), int(cursor['y'])]
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.SubprocessError):
        cursor = None
    return dict(schema=2, instance=hc.instance, clients=clients, monitors=monitors, cursor=cursor,
                activewindow=hc.query('activewindow'), activeworkspace=hc.query('activeworkspace'),
                metrics=metrics, trees=workspace_trees(clients, monitors, metrics))


class Restore:
    def __init__(self, hc, saved, journal=None):
        self.hc, self.saved, self.journal = hc, saved, journal
        self.original = {c['address']: c for c in saved['clients'] if c.get('mapped', True)}
        self.detached = {}
        self.errors = []
        self.collecting = None
        self.leave = None
        self.scratch_workspaces = set()

    def query(self, name):
        if self.collecting is not None:
            return self.predicted[name]
        return self.hc.query(name)

    def dispatch(self, commands):
        if self.collecting is None:
            return self.hc.batch(commands)
        self.collecting.extend(commands)
        # Track only effects used by later planner steps. Geometry of native
        # trees is supplied by rebuild_plan, and is checked against Hyprland later.
        clients = self.predicted['clients']
        monitors = self.predicted['monitors']
        for name, arg in commands:
            address = arg.removeprefix('address:')
            window = next((c for c in clients if c['address'] == address), None)
            if name in ('setfloating', 'settiled', 'pin') and window:
                members = window['grouped'] or [address]
                for c in clients:
                    if c['address'] in members:
                        if name == 'pin':
                            c['pinned'] = not c['pinned']
                        else:
                            c['floating'] = name == 'setfloating'
            elif name == 'focuswindow' and window:
                self.predicted['activewindow'] = {'address': address}
                for c in clients:
                    if c['address'] in window['grouped']:
                        c['acceptsInput'] = c['address'] == address
                for m in monitors:
                    m['focused'] = m['id'] == window['monitor']
                    if m['focused']:
                        if window['workspace']['name'].startswith('special:'):
                            m['specialWorkspace'] = copy.deepcopy(window['workspace'])
                        else:
                            m['activeWorkspace'] = copy.deepcopy(window['workspace'])
            elif name == 'fullscreenstate':
                active = self.predicted['activewindow'].get('address')
                for c in clients:
                    if c['address'] == active:
                        c['fullscreen'], c['fullscreenClient'] = map(int, arg.split())
            elif name in ('togglegroup', 'moveintogroup'):
                active = self.predicted['activewindow'].get('address')
                window = next(c for c in clients if c['address'] == active)
                if name == 'togglegroup':
                    members = window['grouped'][:]
                    for c in clients:
                        if c['address'] in members:
                            c['grouped'] = []
                    if not members:
                        window['grouped'] = [active]
                else:
                    target = self.original[active]['grouped']
                    root = next(c for c in clients if c['address'] != active
                                and c['address'] in target and c['grouped'])
                    members = root['grouped']+[active]
                    for c in clients:
                        if c['address'] in members:
                            c['grouped'] = members[:]
                            c['acceptsInput'] = c['address'] == active
            elif name in ('resizewindowpixel', 'movewindowpixel'):
                geometry, address = arg.split(',address:')
                for c in clients:
                    if c['address'] == address and c['floating']:
                        c['size' if name == 'resizewindowpixel' else 'at'] = list(map(int, geometry.split()[1:]))
            elif name == 'movetoworkspacesilent':
                target, address = arg.split(',address:')
                ws = next(c['workspace'] for c in self.original.values()
                          if workspace_arg(c['workspace']) == target)
                for c in clients:
                    if c['address'] == address:
                        c['workspace'] = copy.deepcopy(ws)
            elif name == 'moveworkspacetomonitor':
                target, monitor = arg.split()
                destination = next(m for m in monitors if m['name'] == monitor)
                for c in clients:
                    if workspace_arg(c['workspace']) == target:
                        c['monitor'] = destination['id']
                for ws in self.predicted['workspaces']:
                    if workspace_arg(ws) == target:
                        ws['monitor'] = monitor
                for m in monitors:
                    if m['name'] != monitor and workspace_arg(m['activeWorkspace']) == target:
                        # Hyprland selects another workspace on the source monitor.
                        # Its identity is irrelevant: active_workspaces repairs it.
                        m['activeWorkspace'] = dict(id=0, name='')
            elif name == 'focusmonitor':
                for m in monitors:
                    m['focused'] = m['name'] == arg
            elif name == 'workspace':
                monitor = next(m for m in monitors if m.get('focused'))
                # Workspace visits may clear or choose window focus; require an
                # explicit final focus instead of trusting the pre-switch target.
                self.predicted['activewindow'] = {}
                ws = next((ws for ws in self.predicted['workspaces'] if workspace_arg(ws) == arg), None)
                if ws is None:
                    ws = next((m['activeWorkspace'] for m in self.saved['monitors']
                               if workspace_arg(m['activeWorkspace']) == arg), None)
                monitor['activeWorkspace'] = (dict(id=ws['id'], name=ws['name']) if ws
                                              else dict(id=int(arg), name=arg))
                monitor['specialWorkspace'] = dict(id=0, name='')
            elif name == 'togglespecialworkspace':
                monitor = next(m for m in monitors if m.get('focused'))
                target = 'special:'+arg
                ws = next((c['workspace'] for c in self.original.values()
                           if c['workspace']['name'] == target), dict(id=-99, name=target))
                monitor['specialWorkspace'] = (dict(id=0, name='')
                    if monitor.get('specialWorkspace', {}).get('name') == target else copy.deepcopy(ws))

    def live(self):
        clients = self.query('clients')
        validate_clients(clients)
        return {c['address']: c for c in clients}

    def pairs(self, current):
        return [(s, current[a]) for a, s in self.original.items()
                if a in current and same_window(s, current[a])]

    def attempt(self, operation):
        try:
            operation()
        except Exception as error:
            self.errors.append(str(error))
            report(str(error))

    def revive_commands(self, monitor):
        workspaces = self.query('workspaces')
        monitors = self.query('monitors')
        reserved = [ws['id'] for ws in workspaces]
        reserved += [m['activeWorkspace']['id'] for m in monitors+self.saved['monitors']]
        reserved += [c['workspace']['id'] for c in self.live().values()]
        reserved += [c['workspace']['id'] for c in self.original.values()]
        scratch = max([0]+reserved)+100
        return [('focusmonitor', safe_name(monitor['name'])), ('workspace', str(scratch)),
                ('workspace', workspace_arg(monitor['activeWorkspace']))]

    def revive(self, monitor, prefix=()):
        wiggle = self.revive_commands(monitor)
        if self.collecting is not None:
            self.dispatch(prefix)
            self.scratch_workspaces.add(int(wiggle[1][1]))
            now = next(m for m in self.query('monitors') if m['name'] == monitor['name'])
            active_special = now.get('specialWorkspace', {}).get('name', '')
            # Close it explicitly so both compositor behaviours (workspace
            # switches preserving or closing specials) have the same plan.
            self.dispatch([wiggle[0]])
            if active_special:
                self.dispatch([('togglespecialworkspace', safe_name(active_special)[8:])])
            self.dispatch(wiggle[1:])
            target_special = monitor.get('specialWorkspace', {}).get('name', '')
            if target_special:
                self.dispatch([('togglespecialworkspace', safe_name(target_special)[8:])])
            return
        last_monitor = next((arg for name, arg in reversed(prefix) if name == 'focusmonitor'), None)
        self.dispatch([*prefix, *(wiggle[1:] if last_monitor == monitor['name'] else wiggle)])
        if self.hc.dry:
            return
        now = next((m for m in self.hc.query('monitors') if m['name'] == monitor['name']), None)
        if not now or not now.get('focused') or now['activeWorkspace'] != monitor['activeWorkspace']:
            raise RuntimeError(f'workspace revive did not return to monitor {monitor["name"]}')
        scratch = int(wiggle[1][1])
        if any(ws['id'] == scratch for ws in self.hc.query('workspaces')):
            raise RuntimeError(f'scratch workspace {scratch} survived revive')
        active_special = now.get('specialWorkspace', {}).get('name', '')
        target_special = monitor.get('specialWorkspace', {}).get('name', '')
        if active_special != target_special:
            commands = []
            if active_special:
                commands.append(('togglespecialworkspace', safe_name(active_special)[8:]))
            if target_special:
                commands.append(('togglespecialworkspace', safe_name(target_special)[8:]))
            self.hc.batch(commands)

    def focus(self, window, warp=True, cursor=None, prefix=()):
        if self.collecting is not None:
            commands = list(prefix)
            if warp:
                live = self.live()[window['address']]
                commands.append(cursor_command(live['at']+live['size']))
            self.dispatch([*commands, ('focuswindow', 'address:'+window['address'])])
            return
        # A live-target warp needs geometry after preceding mutations. Node-cursor
        # plans already supply their warp and can dispatch through focus together.
        if warp and prefix:
            self.hc.batch(prefix)
            prefix = ()
        for attempt in range(2):
            error = None
            try:
                commands = list(prefix) if not attempt else []
                if attempt:
                    live = self.live().get(window['address'])
                    if live is None or not same_window(window, live):
                        raise RuntimeError('focus target is no longer available')
                    monitor = next((m for m in self.hc.query('monitors') if m['id'] == live['monitor']), None)
                    if monitor is None:
                        raise RuntimeError('focus target monitor is no longer available')
                    self.revive(monitor)
                if warp:
                    live = self.live().get(window['address'])
                    if live is None or not same_window(window, live):
                        raise RuntimeError('focus target is no longer available')
                    commands.append(cursor_command(live['at']+live['size']))
                elif cursor and attempt:
                    commands.append(cursor)
                self.hc.batch([*commands, ('focuswindow', 'address:'+window['address'])])
            except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as failure:
                if prefix and not attempt:
                    # A failed rebuild prefix must reach the workspace's recovery
                    # path, rather than retrying only its focus and losing the error.
                    raise
                error = str(failure)
            if self.hc.dry and error is None:
                return
            try:
                active = self.hc.query('activewindow')
            except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as failure:
                active = {'query_error': str(failure)}
                error = str(failure)
            if error is None and active.get('address') == window['address']:
                return
        message = (f'focus failed for {window["address"]}: {error}' if error
                   else f'focus did not reach {window["address"]}')
        message = f'workspace {window["workspace"]["name"]}: {message} after revive retry; workspace step aborted'
        report(f'{message}; activewindow={json.dumps(active)}')
        try:
            report(f'monitors={json.dumps(self.hc.query("monitors"))}')
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as failure:
            report(f'monitors unavailable: {failure}')
        raise RuntimeError(message)

    def checked_commands(self, commands):
        if self.collecting is not None:
            self.dispatch(commands)
            return
        previous = None
        cursor = None
        pending = []
        for name, arg in commands:
            if name == 'focuswindow':
                self.focus(self.original[arg.removeprefix('address:')],
                           warp=previous != 'movecursor', cursor=cursor, prefix=pending)
                pending = []
            else:
                pending.append((name, arg))
                if name == 'movecursor':
                    cursor = (name, arg)
            previous = name
        self.dispatch(pending)

    def fullscreen(self, window, modes):
        live = self.live().get(window['address'])
        if live is None or not same_window(window, live):
            return
        if any(modes) and not window['floating'] and live['floating']:
            self.focus(window)
            self.dispatch([('settiled', 'address:'+window['address'])])
            live = self.live().get(window['address'])
            if self.collecting is None and not self.hc.dry and (live is None or not same_window(window, live) or live['floating']):
                raise RuntimeError(f'{window["address"]} must be tiled before fullscreen restore')
        if self.collecting is None and [live['fullscreen'], live.get('fullscreenClient', live['fullscreen'])] == modes:
            return
        self.focus(window)
        self.dispatch([('fullscreenstate', f'{modes[0]} {modes[1]}')])
        if self.collecting is None and not self.hc.dry:
            live = self.live().get(window['address'])
            if (live is None or not same_window(window, live)
                    or [live['fullscreen'], live.get('fullscreenClient', live['fullscreen'])] != modes):
                raise RuntimeError(f'{window["address"]} fullscreen state did not reach {modes}')

    def placement(self):
        current = self.live()
        pairs = self.pairs(current)
        for saved, now in pairs:
            if now['fullscreen'] or now.get('fullscreenClient', now['fullscreen']):
                self.attempt(lambda: self.fullscreen(saved, [0, 0]))
        commands = []
        for saved, now in pairs:
            if now['pinned'] and any(saved[field] != now[field] for field in
                                     ('pinned', 'workspace', 'monitor', 'floating', 'at', 'size')):
                commands.append(('pin', 'address:'+saved['address']))
            if self.collecting is not None or saved['workspace'] != now['workspace']:
                commands.append(('movetoworkspacesilent', workspace_arg(saved['workspace'])+',address:'+saved['address']))
        monitors = self.query('monitors')
        names = {m['name'] for m in monitors}
        workspaces = {str(ws['id']): ws for ws in self.query('workspaces')}
        existing = set(workspaces)
        placements = {str(m['activeWorkspace']['id']): (m['activeWorkspace'], m['name'])
                      for m in self.saved['monitors'] if str(m['activeWorkspace']['id']) in existing}
        for saved, _ in pairs:
            monitor = next((m for m in self.saved['monitors'] if m['id'] == saved['monitor']), None)
            if monitor and not saved['workspace']['name'].startswith('special:'):
                placements[str(saved['workspace']['id'])] = (saved['workspace'], monitor['name'])
        for ws, name in placements.values():
            if name in names:
                monitor = next(m for m in monitors if m['name'] == name)
                if (self.collecting is None and workspaces.get(str(ws['id']), {}).get('monitor') == name
                        and all(n['monitor'] == monitor['id'] for s, n in pairs
                                if s['workspace']['id'] == ws['id'])):
                    continue
                commands.append(('moveworkspacetomonitor', workspace_arg(ws)+' '+safe_name(name)))
        self.checked_commands(commands)

    def restore_groups(self):
        current = self.live()
        pairs = self.pairs(current)
        survivors = {s['address'] for s, _ in pairs}
        mismatched = [(s, n) for s, n in pairs
                      if [a for a in s['grouped'] if a in survivors] != n['grouped']]
        if not mismatched:
            return
        # Isolate the affected workspaces so directional group joins have one neighbour.
        workspaces = {s['workspace']['id'] for s, _ in mismatched}
        affected = [n for n in current.values() if n['workspace']['id'] in workspaces]
        self.detached.update({n['address']: n for n in affected
                              if n['address'] not in survivors and not n['floating']})
        commands = [('setfloating', 'address:'+n['address']) for n in affected]
        seen = set()
        for _, n in mismatched:
            group = tuple(n['grouped'])
            if group and group not in seen:
                seen.add(group)
                commands.extend([('focuswindow', 'address:'+n['address']), ('togglegroup', '')])
        self.checked_commands(commands)
        seen = set()
        for saved, _ in pairs:
            members = tuple(a for a in saved['grouped'] if a in survivors)
            if not members or members in seen or saved['workspace']['id'] not in workspaces:
                continue
            seen.add(members)
            root = self.original[members[0]]
            self.checked_commands([('focuswindow', 'address:'+root['address']),
                           ('settiled', 'address:'+root['address']),
                           ('focuswindow', 'address:'+root['address']), ('togglegroup', '')])
            for address in members[1:]:
                self.checked_commands([('focuswindow', 'address:'+root['address']), ('layoutmsg', 'preselect r'),
                               ('settiled', 'address:'+address), ('focuswindow', 'address:'+address),
                               ('moveintogroup', 'l')])
            self.dispatch([('setfloating', 'address:'+root['address'])])
        # A new window detached from a saved group keeps a normal native tile.
        self.dispatch([('settiled', 'address:'+n['address']) for n in affected
                       if n['address'] not in survivors and not n['floating']])

    def correct(self, tree):
        if 'members' in tree:
            return
        first, second = tree['children']
        current = self.live()
        current_boxes = []
        for tile in leaves(first):
            c = current.get(tile['representative'])
            if c:
                current_boxes.append([c['at'][0], c['at'][1]-tile['header'],
                                      c['size'][0], c['size'][1]+tile['header']])
        rep = leaves(first)[0]['representative']
        if current_boxes and rep in current:
            axis = 0 if tree['split'] == 'h' else 1
            delta = first['box'][axis+2]-bounds(current_boxes)[axis+2]
            size = list(current[rep]['size'])
            size[axis] += delta
            if delta and min(size) > 0:
                self.dispatch([resize_command(rep, *size)])
        self.correct(first)
        self.correct(second)

    def tiles(self):
        for ws, saved_tree in self.saved['trees'].items():
            self.attempt(lambda: self.rebuild_workspace(ws, saved_tree))

    def rebuild_workspace(self, ws, saved_tree):
        current = self.live()
        survivors = {s['address'] for s, _ in self.pairs(current)}
        tree = prune_tree(saved_tree, survivors)
        if not tree:
            return
        saved_members = {a for t in leaves(saved_tree) for a in t['members']}
        native = [c for c in current.values() if str(c['workspace']['id']) == ws and not c['floating']]
        extras = [c for c in native if c['address'] not in saved_members]
        churn = saved_members != {a for t in leaves(tree) for a in t['members']} or bool(extras)
        had_fullscreen = any(self.original[a]['fullscreen']
                             or self.original[a].get('fullscreenClient', 0)
                             for t in leaves(tree) for a in t['members'])
        for c in current.values():
            if (str(c['workspace']['id']) == ws and c['address'] in self.original
                    and (c['fullscreen'] or c.get('fullscreenClient', 0))):
                self.fullscreen(self.original[c['address']], [0, 0])
        current = self.live()
        differences = tile_differences(tree, list(current.values()))
        if self.collecting is None and not differences and not had_fullscreen:
            return
        report(f'workspace {ws}: rebuilding {len(leaves(tree))} tiles')
        self.detached.update({c['address']: c for c in extras})
        commands = [('setfloating', 'address:'+c['address']) for c in extras] + [
            (name, arg) for name, arg in rebuild_plan(tree)
            if self.collecting is not None or name != 'setfloating'
            or not current[arg.removeprefix('address:')]['floating']]
        self.checked_commands(commands)
        if self.collecting is not None:
            for tile in leaves(tree):
                for address in tile['members']:
                    current[address]['at'] = tile['rect'][:2]
                    current[address]['size'] = tile['rect'][2:]
            self.dispatch([('settiled', 'address:'+c['address']) for c in extras])
            if churn:
                report(f'workspace {ws}: windows opened/closed; retained survivor order and appended new tiles')
            return
        current = self.live()
        if not self.hc.dry and tile_differences(tree, list(current.values())):
            self.checked_commands(rebuild_plan(tree))
            self.correct(tree)
            current = self.live()
        errors = tile_differences(tree, list(current.values()))
        self.dispatch([('settiled', 'address:'+c['address']) for c in extras])
        if churn:
            report(f'workspace {ws}: windows opened/closed; retained survivor order and appended new tiles')
        elif errors and not self.hc.dry:
            for error in errors:
                report(error)
            raise RuntimeError(f'workspace {ws}: native tile verification failed at 0 px')

    def finish(self):
        current = self.live()
        commands = []
        errors_before = len(self.errors)

        def restore_window(saved, now):
            address = 'address:'+saved['address']
            if saved['floating'] != now['floating'] or self.collecting is not None and saved['floating']:
                if not saved['floating']:
                    pending = list(commands)
                    commands.clear()
                    self.dispatch(pending)
                    self.focus(saved)
                commands.append(('setfloating' if saved['floating'] else 'settiled', address))
            if saved['floating']:
                if self.collecting is not None or not now['floating'] or saved['size'] != now['size']:
                    commands.append(resize_command(saved['address'], *saved['size']))
                if self.collecting is not None or not now['floating'] or saved['at'] != now['at']:
                    commands.append(('movewindowpixel', f'exact {saved["at"][0]} {saved["at"][1]},'+address))
            if saved['pinned'] != now['pinned']:
                commands.append(('pin', address))

        for saved, now in self.pairs(current):
            self.attempt(lambda: restore_window(saved, now))
        self.attempt(lambda: self.dispatch(commands))
        if self.collecting is None and len(self.errors) != errors_before:
            # A batch can have applied only a prefix. Re-query before retrying so
            # pin toggles cannot undo a successful prefix, and repair every survivor.
            for saved, now in self.pairs(self.live()):
                commands.clear()
                self.attempt(lambda: restore_window(saved, now))
                self.attempt(lambda: self.dispatch(commands))
        for saved, _ in self.pairs(self.live()):
            modes = [saved['fullscreen'], saved.get('fullscreenClient', saved['fullscreen'])]
            self.attempt(lambda: self.fullscreen(saved, modes))
        # Focusing a member is the only way to choose a group's active tab.
        for saved, now in self.pairs(self.live()):
            if saved['grouped'] and saved.get('acceptsInput') is True and now.get('acceptsInput') is False:
                self.attempt(lambda: self.focus(saved))
        self.attempt(self.active_workspaces)

    def restore_focus(self):
        focused = self.saved.get('activewindow', {}).get('address')
        current = self.live()
        if focused in self.original and focused in current and same_window(self.original[focused], current[focused]):
            window = current[focused]
            monitors = self.query('monitors')
            monitor = next((m for m in monitors if m['id'] == window['monitor']), None)
            visible = monitor and window['workspace'] in (monitor['activeWorkspace'], monitor.get('specialWorkspace'))
            if (self.collecting is None and not self.hc.dry and visible and (monitor.get('focused') or self.split_focus())
                    and self.query('activewindow').get('address') == focused):
                return
            self.attempt(lambda: self.focus(self.original[focused], warp=False))

    def split_focus(self):
        """True when state A had the focused window on one monitor and the pointer on another."""
        focus = self.original.get(self.saved.get('activewindow', {}).get('address'))
        wanted = next((m for m in self.saved['monitors'] if m.get('focused')), None)
        return bool(focus and wanted and focus['monitor'] != wanted['id'])

    def restore_monitor_focus(self):
        focus = self.original.get(self.saved.get('activewindow', {}).get('address'))
        wanted = next((m for m in self.saved['monitors'] if m.get('focused')), None)
        cursor = self.saved.get('cursor')
        if not self.split_focus() or not cursor:
            return
        now = next((m for m in self.query('monitors') if m['name'] == wanted['name']), None)
        if now is None or now.get('focused'):
            return
        width, height = now['width'], now['height']
        if now.get('transform', 0) % 2:
            width, height = height, width
        scale = now.get('scale', 1)
        if not (now['x'] <= cursor[0] < now['x']+width/scale and now['y'] <= cursor[1] < now['y']+height/scale):
            return
        # Putting the pointer back moves the focused monitor; undo it if it also stole the window focus.
        self.dispatch([('movecursor', f'{cursor[0]} {cursor[1]}')])
        if not self.hc.dry and self.query('activewindow').get('address') != focus['address']:
            self.attempt(lambda: self.focus(focus, warp=False))

    def active_workspaces(self, before_rebuild=False):
        current = {m['name']: copy.deepcopy(m) for m in self.query('monitors')}
        clients = self.live()
        commands, focuses = [], []
        monitors = sorted(self.saved['monitors'], key=lambda m: bool(m.get('focused')))
        if self.collecting is not None and before_rebuild:
            # off all synchronously puts monitors on one workspace. Repair every
            # monitor before any window mutation, even if the pre-close query
            # matched A, and revive the saved focused monitor last.
            focused = next((m for m in monitors if m.get('focused')), None)
            if focused is None or any(m['name'] not in current for m in monitors):
                raise RuntimeError('saved monitor unavailable for atomic workspace repair')
            for saved in monitors:
                if saved is focused:
                    self.revive(saved)
                    continue
                self.dispatch([('focusmonitor', safe_name(saved['name']))])
                active_special = current[saved['name']].get('specialWorkspace', {}).get('name', '')
                if active_special:
                    self.dispatch([('togglespecialworkspace', safe_name(active_special)[8:])])
                self.dispatch([('workspace', workspace_arg(saved['activeWorkspace']))])
                target_special = saved.get('specialWorkspace', {}).get('name', '')
                if target_special:
                    self.dispatch([('togglespecialworkspace', safe_name(target_special)[8:])])
            return
        for saved in monitors:
            now = current.get(saved['name'])
            if now is None:
                continue
            target = saved['activeWorkspace']
            active_special = now.get('specialWorkspace', {}).get('name', '')
            target_special = saved.get('specialWorkspace', {}).get('name', '')
            needs_workspace = now['activeWorkspace'] != target
            needs_special = active_special != target_special
            needs_focus = saved.get('focused') and not now.get('focused')
            if not (needs_workspace or needs_special or needs_focus):
                continue
            window = next((c for c in clients.values() if c['monitor'] == now['id']
                           and c['workspace'] == target and not c.get('hidden')), None)
            if window and not before_rebuild:
                focuses.append(window)
            visit = needs_workspace and (before_rebuild or not window)
            if needs_special or visit or (needs_focus and not window):
                commands.append(('focusmonitor', safe_name(saved['name'])))
            if self.collecting is not None and visit and active_special:
                commands.append(('togglespecialworkspace', safe_name(active_special)[8:]))
                active_special = ''
                needs_special = bool(target_special)
            if visit:
                commands.append(('workspace', workspace_arg(target)))
            if active_special and needs_special:
                commands.append(('togglespecialworkspace', safe_name(active_special)[8:]))
            if target_special and needs_special:
                commands.append(('togglespecialworkspace', safe_name(target_special)[8:]))
        focused = next((m for m in monitors if m.get('focused') and m['name'] in current), None)
        if commands or before_rebuild and focused and not current[focused['name']].get('focused'):
            if focused is None:
                raise RuntimeError('saved focused monitor is unavailable for workspace revive')
            self.revive(focused, commands)
        for window in focuses:
            self.attempt(lambda: self.focus(window))
        # Focuses on other monitors can have changed focus even when the saved
        # monitor needed no workspace repair in the initial comparison.
        if focuses and focused:
            window = next((c for c in clients.values() if c['monitor'] == current[focused['name']]['id']
                           and c['workspace'] == focused['activeWorkspace'] and not c.get('hidden')), None)
            if window and window not in focuses:
                self.attempt(lambda: self.focus(window))
            elif not window:
                now = next(m for m in self.query('monitors') if m['name'] == focused['name'])
                if not now.get('focused') or now['activeWorkspace'] != focused['activeWorkspace']:
                    self.revive(focused)

    def verify(self):
        current = self.live()
        pairs = self.pairs(current)
        alive = {s['address'] for s, _ in pairs}
        changed_tiles = {s['workspace']['id'] for a, s in self.original.items()
                         if not s['floating'] and (a not in alive or current[a]['floating']
                                                    or s['workspace'] != current[a]['workspace'])}
        changed_tiles.update(c['workspace']['id'] for a, c in current.items()
                             if c.get('mapped', True) and not c['floating']
                             and (a not in alive or self.original[a]['floating']
                                  or self.original[a]['workspace'] != c['workspace']))
        errors = []
        for saved, now in pairs:
            for field in ('workspace', 'monitor', 'floating', 'pinned', 'fullscreen', 'fullscreenClient'):
                if saved.get(field, saved['fullscreen']) != now.get(field, now['fullscreen']):
                    errors.append(f'{saved["address"]} {field}: {now.get(field)} != {saved.get(field)}')
            if [a for a in saved['grouped'] if a in alive] != now['grouped']:
                errors.append(f'{saved["address"]} group order/membership differs')
            if (saved['grouped'] and saved.get('acceptsInput') is True and now.get('acceptsInput') is False
                    and len(now['grouped']) == len(saved['grouped'])):
                errors.append(f'{saved["address"]} is no longer the active tab of its group')
            if saved['floating'] or saved['workspace']['id'] not in changed_tiles:
                for field in ('at', 'size'):
                    if saved[field] != now[field]:
                        errors.append(f'{saved["address"]} {field}: {now[field]} != {saved[field]}')
        monitors = {m['name']: m for m in self.query('monitors')}
        for saved in self.saved['monitors']:
            now = monitors.get(saved['name'])
            if not now:
                errors.append(f'monitor {saved["name"]} disconnected')
                continue
            for field in ('activeWorkspace', 'specialWorkspace', 'focused'):
                if saved.get(field) != now.get(field):
                    if field == 'focused' and self.split_focus():
                        # Not reachable when the pointer then sat over another window; not a failed restore.
                        report(f'note: focused monitor differs on {saved["name"]} (pointer was away from the focused window)')
                        continue
                    errors.append(f'monitor {saved["name"]} {field} differs')
        focus = self.saved.get('activewindow', {}).get('address')
        active = self.query('activewindow').get('address')
        if (focus in alive and active != focus) or (not focus and active):
            errors.append(f'focused window differs from {focus}')
        if errors:
            for error in errors:
                report(error)
            raise RuntimeError('state verification failed; snapshot retained')

    def atomic(self):
        options, restore_cursor, _ = self.leave
        wanted = {'dwindle:smart_resizing': 0, 'dwindle:use_active_for_splits': 1,
                  'dwindle:preserve_split': 1, 'group:auto_group': 0,
                  'group:group_on_movetoworkspace': 0, 'binds:ignore_group_lock': 1}
        previous = {name: self.hc.query('getoption', name)['int'] for name in wanted}
        if self.journal and not self.hc.dry:
            try:
                original = json.loads(self.journal.read_text())
                previous.update({k: int(v) for k, v in original.items() if k in wanted})
            except (OSError, ValueError, TypeError, AttributeError):
                pass
            save_atomic(self.journal, previous)
        self.predicted = {name: self.hc.query(name)
                          for name in ('clients', 'monitors', 'workspaces', 'activewindow')}
        validate_clients(self.predicted['clients'])
        # Plan against close's synchronous re-tiling. Workspace/monitor and
        # geometry facts from this query are uncertain after close, so restore
        # them with set-style dispatches regardless of their pre-close values.
        # Close preserves pin, group membership and special visibility; toggles
        # below are still chosen from those known states and tracked as emitted.
        for client in self.predicted['clients']:
            if client.get('mapped', True):
                client['floating'] = False
        commands = [('spatialoverview:overview', 'off all')]
        commands.extend(('keyword', name+' '+str(value)) for name, value in wanted.items())
        self.collecting = commands
        try:
            self.active_workspaces(before_rebuild=True)
            self.placement()
            self.restore_groups()
            self.tiles()
            self.reattach_detached()
            self.finish()
            commands.extend(('keyword', name+' '+str(value)) for name, value in previous.items())
            commands.extend(('keyword', name+' '+str(options[name])) for name in CANVAS_OPTIONS)
            self.restore_focus()
            pointer = restore_cursor(collect=commands)
            if self.errors:
                raise RuntimeError('; '.join(self.errors))
        finally:
            self.collecting = None
        self.hc.batch(commands)
        if not self.hc.dry:
            if canvas_count(self.hc):
                raise RuntimeError('canvas reopened during atomic restore')
            self.verify()
            if self.scratch_workspaces.intersection(ws['id'] for ws in self.hc.query('workspaces')):
                raise RuntimeError('scratch workspace survived atomic restore')
            if pointer:
                cursor = self.hc.query('cursorpos')
                if f'{int(cursor["x"])} {int(cursor["y"])}' != pointer[1]:
                    raise RuntimeError('pointer differs after atomic restore')
        restore_cursor(completed=True)

    def run(self, before_focus=None):
        if self.leave:
            try:
                self.atomic()
                return True
            except Exception as error:
                report(f'atomic restore needs multi-step repair: {error}')
                self.errors.clear()
                # A partially applied batch can also have reopened the canvas.
                # Even a rejected close retry must not skip native-window repair.
                self.attempt(self.leave[2])
        with temporary_options(self.hc, {'dwindle:smart_resizing': 0, 'dwindle:use_active_for_splits': 1,
                                         'dwindle:preserve_split': 1, 'group:auto_group': 0,
                                         'group:group_on_movetoworkspace': 0, 'binds:ignore_group_lock': 1},
                               self.journal):
            self.attempt(self.placement)
            self.attempt(lambda: self.active_workspaces(before_rebuild=True))
            self.attempt(self.restore_groups)
            self.attempt(self.tiles)
            # Reattach new native windows before fullscreen and final monitor visits.
            self.reattach_detached()
            self.attempt(self.finish)
        if before_focus:
            before_focus()
        self.restore_focus()
        # The leave callback already restored the current pointer exactly once.
        # A standalone restore may still use the snapshot's older pointer position.
        if before_focus is None:
            self.attempt(self.restore_monitor_focus)
        if self.errors:
            raise RuntimeError('; '.join(self.errors))
        if not self.hc.dry:
            self.verify()

    def reattach_detached(self):
        for address, window in self.detached.items():
            current = self.live().get(address)
            if current and same_window(window, current) and current['floating']:
                def reattach():
                    self.focus(current)
                    self.dispatch([('settiled', 'address:'+address)])
                self.attempt(reattach)


def canvas_state(hc, timeout=None):
    state = hc.query('spatialoverview') if timeout is None else hc.query('spatialoverview', timeout=timeout)
    if not isinstance(state['screens'], list):
        raise ValueError('invalid canvas state')
    return state


def canvas_screens(hc, timeout=None):
    return canvas_state(hc, timeout)['screens']


def canvas_count(hc):
    return len(canvas_screens(hc))


def settle_canvas_camera(hc, initial_state=None, ready_timeout=1.5, settle_timeout=.6):
    """Best-effort focused-monitor camera anchoring; return whether a correction was issued."""
    if hc.dry:
        return False
    issued = False
    try:
        deadline = time.monotonic()+ready_timeout
        overview = initial_state if initial_state is not None else canvas_state(hc, timeout=ready_timeout)
        while True:
            screens = overview['screens']
            # Older plugins and transport doubles have no observable camera data.
            if not any('monitor' in screen for screen in screens):
                return False
            if (isinstance(overview.get('leader'), str) and overview['leader']
                    and all('monitor' in screen and 'view' in screen
                            and screen.get('navigating') is True for screen in screens)):
                break
            remaining = deadline-time.monotonic()
            if remaining <= 0:
                return False
            time.sleep(min(.02, remaining))
            overview = canvas_state(hc, timeout=remaining)

        monitor = next((m for m in hc.query('monitors') if m.get('focused')), None)
        if monitor is None or not any(s['monitor'] == monitor['name'] for s in screens):
            return False
        anchor = monitor['name']
        width, height = monitor['width'], monitor['height']
        if monitor.get('transform', 0) % 2:
            width, height = height, width
        scale = monitor.get('scale', 1)
        centre = (monitor['x']+width/scale/2, monitor['y']+height/scale/2)

        def centred(state):
            screen = next((s for s in state['screens'] if s.get('monitor') == anchor), None)
            if state.get('leader') != anchor or screen is None:
                return False
            x, y, w, h = screen['view']
            return (x+w/2-centre[0])**2+(y+h/2-centre[1])**2 <= 1.5**2

        def wait_centred():
            deadline = time.monotonic()+settle_timeout
            while True:
                remaining = deadline-time.monotonic()
                if remaining <= 0:
                    return False
                if centred(canvas_state(hc, timeout=remaining)):
                    return True
                time.sleep(min(.02, remaining))

        if centred(overview):
            return False
        issued = True
        hc.batch([('spatialoverview:canvas', 'viewport 0 0')])
        if wait_centred():
            return True
        # An already-zero follower needs a camera change across separate frames.
        hc.batch([('spatialoverview:canvas', 'viewport 1 0')])
        time.sleep(.05)
        hc.batch([('spatialoverview:canvas', 'viewport 0 0')])
        if not wait_centred():
            report(f'warning: canvas camera did not settle on {anchor}; continuing enter')
    except Exception as error:
        report(f'warning: could not settle canvas camera: {error}; continuing enter')
    return issued


def zoom_to_desktop(hc):
    screens = canvas_screens(hc)
    if not screens or not any(screen.get('navigating', False) for screen in screens):
        return
    hc.batch([('spatialoverview:overview', 'toggle all')])
    if hc.dry:
        report('would wait up to 4 s for every canvas screen to finish zooming to the desktop')
        return
    deadline = time.monotonic()+4
    while True:
        remaining = deadline-time.monotonic()
        if remaining <= 0:
            break
        try:
            screens = canvas_screens(hc, timeout=remaining)
        except subprocess.TimeoutExpired:
            break
        # The plugin fades its distortion, dim and minimap on the same animation as the zoom, so cutting
        # the tail short shows as a hop. It reports three decimals: wait for the zoom to round to 1.
        if not screens or all(not screen.get('navigating', False) and screen.get('zoom', 0) >= .9995
                              for screen in screens):
            return
        time.sleep(.016)
    report('warning: canvas zoom did not finish within 4 s; continuing restore')


def save_atomic(path, data):
    fd, temporary = tempfile.mkstemp(prefix=path.name+'.', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(data, stream, separators=(',', ':'))
            stream.write('\n')
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


CANVAS_REMEMBER = 'plugin:spatialoverview:canvas:remember_layout'
CANVAS_AUTO_PLACE = 'plugin:spatialoverview:canvas:auto_place'
CANVAS_OPTIONS = (CANVAS_REMEMBER, CANVAS_AUTO_PLACE)
# polish: optional glass setting stays out of the atomic close/rebuild batch.
CANVAS_GLASS = 'plugin:hyprglass:manage_window_blur'
GLASS_DESKTOP_FRAME_DELAY = .15
# polish: glass on at this opacity is the measured closest look to glass off, so the switch hides in a fade.
GLASS_OPACITY = 'plugin:hyprglass:glass_opacity'
GLASS_MATCH, GLASS_FADE, GLASS_FADE_STEPS = .3, .2, 10
ANIMATIONS = 'animations:enabled'


def read_canvas_options(journal):
    try:
        data = json.loads(journal.read_text())
        previous = {name: int(data[name]) for name in CANVAS_OPTIONS}
        # polish: older journals do not contain the optional hyprglass value.
        if CANVAS_GLASS in data:
            previous[CANVAS_GLASS] = int(data[CANVAS_GLASS])
        if GLASS_OPACITY in data:
            previous[GLASS_OPACITY] = float(data[GLASS_OPACITY])
        if ANIMATIONS in data:
            previous[ANIMATIONS] = int(data[ANIMATIONS])
        return previous
    except FileNotFoundError:
        return None
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise RuntimeError(f'could not read canvas option journal: {error}') from error


def glass_option(hc, name):
    # polish: absent/unloaded hyprglass is optional; None means leave the option alone.
    try:
        return float(hc.query('getoption', name)['float' if name == GLASS_OPACITY else 'int'])
    except (RuntimeError, OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired):
        return None


def fade_glass(hc, start, end):
    # polish: smoothstep; the final value is written even when a step is interrupted.
    try:
        for step in range(1, 0 if hc.dry or start == end else GLASS_FADE_STEPS):
            x = step/GLASS_FADE_STEPS
            hc.keyword(GLASS_OPACITY, round(start+(end-start)*x*x*(3-2*x), 3))
            time.sleep(GLASS_FADE/GLASS_FADE_STEPS)
    finally:
        hc.keyword(GLASS_OPACITY, end)


def restore_glass(hc, previous):
    # polish: switch glass on at the matching opacity, then fade to the configured one.
    opacity = previous.get(GLASS_OPACITY)
    if glass_option(hc, GLASS_OPACITY) is None:
        opacity = None
    try:
        if opacity is not None:
            hc.keyword(GLASS_OPACITY, min(GLASS_MATCH, opacity))
        restore_option_values(hc, {CANVAS_GLASS: previous[CANVAS_GLASS]})
    finally:
        if opacity is not None:
            fade_glass(hc, min(GLASS_MATCH, opacity), opacity)


def restore_option_values(hc, previous):
    errors = []
    for name, value in reversed(list(previous.items())):
        # polish: a plugin may also disappear between journalling and recovery.
        if name in (CANVAS_GLASS, GLASS_OPACITY) and glass_option(hc, name) is None:
            continue
        try:
            hc.keyword(name, value)
        except Exception as error:
            errors.append(str(error))
    if errors:
        raise RuntimeError('could not restore temporary options: '+'; '.join(errors))


def restore_canvas_options(hc, journal, previous=None, canvas_restored=False):
    animation_restored = False
    # polish: retain the journal if glass restoration fails; always attempt it last.
    glass_restored = False
    try:
        if previous is None:
            previous = read_canvas_options(journal)
        if previous is None:
            animation_restored = True
            return
        errors = []
        try:
            if not canvas_restored:
                restore_option_values(hc, {name: previous[name] for name in CANVAS_OPTIONS})
        except Exception as error:
            errors.append(str(error))
        finally:
            if ANIMATIONS in previous:
                try:
                    if hc.dry:
                        report(f'would restore {ANIMATIONS} to {previous[ANIMATIONS]}')
                    hc.keyword(ANIMATIONS, previous[ANIMATIONS])
                    animation_restored = True
                except Exception as error:
                    errors.append(str(error))
            else:
                animation_restored = True
        if errors:
            raise RuntimeError('could not restore temporary options: '+'; '.join(errors))
    finally:
        # polish: after zoom/rebuild, including interrupted option cleanup.
        try:
            if previous and CANVAS_GLASS in previous:
                restore_glass(hc, previous)
            glass_restored = True
        finally:
            # Keep either original recoverable if its restore was refused.
            if not hc.dry and animation_restored and glass_restored:
                journal.unlink(missing_ok=True)


def journal_animations(hc, journal):
    current = hc.query('getoption', ANIMATIONS)['int']
    previous = read_canvas_options(journal)
    if previous is None:
        previous = {name: hc.query('getoption', name)['int'] for name in CANVAS_OPTIONS}
    # A killed leave may already have forced the live value to zero.
    previous.setdefault(ANIMATIONS, current)
    if hc.dry:
        report(f'would journal {ANIMATIONS}={previous[ANIMATIONS]} in {journal}')
        report('would disable animations until restore, pointer, focus and verification finish')
    else:
        save_atomic(journal, previous)
    return previous


def open_canvas(hc, saved, journal):
    previous = {}
    toggle_started = False
    # polish: a failed open must release its temporary glass setting too.
    opened = False
    try:
        previous = read_canvas_options(journal)
        if previous is None:
            previous = {name: hc.query('getoption', name)['int'] for name in CANVAS_OPTIONS}
        # polish: absent/unloaded hyprglass is optional, never an entry failure.
        glass = int(glass_option(hc, CANVAS_GLASS) or 0)
        opacity = glass_option(hc, GLASS_OPACITY) if glass else None
        if glass != 0:
            previous.setdefault(CANVAS_GLASS, glass)
            if opacity is not None:
                previous.setdefault(GLASS_OPACITY, opacity)
            if not hc.dry:
                save_atomic(journal, previous)
        elif not hc.dry and not journal.exists():
            # polish: preserve the original mandatory-option journal without glass.
            save_atomic(journal, previous)
        if glass != 0:
            # polish: separate keyword, then a desktop frame before the toggle batch.
            if opacity is not None:
                fade_glass(hc, opacity, min(GLASS_MATCH, previous[GLASS_OPACITY]))
            hc.keyword(CANVAS_GLASS, 0)
            if opacity is not None:
                # polish: opacity has no visible effect while glass is off.
                hc.keyword(GLASS_OPACITY, previous[GLASS_OPACITY])
            elif not hc.dry:
                time.sleep(GLASS_DESKTOP_FRAME_DELAY)
        for name in CANVAS_OPTIONS:
            hc.keyword(name, 0)
        # A dispatch error may arrive after the plugin opened. Keep remember_layout
        # disabled from the moment we dispatch, so its timer cannot persist positions.
        toggle_started = True
        # `toggle all` opens every screen directly in the zoomed-out navigation view.
        hc.batch([('spatialoverview:overview', 'toggle all')])
        overview = None
        if not hc.dry:
            for _ in range(50):
                overview = canvas_state(hc)
                if overview['screens']:
                    break
                time.sleep(.02)
            else:
                raise RuntimeError('canvas did not open; snapshot retained')
        camera_corrected = settle_canvas_camera(hc, overview)
        current = {c['address']: c for c in hc.query('clients')}
        originals = {c['address']: c for c in saved['clients']}
        commands = []
        for address, (x, y, width, height) in canvas_targets(saved).items():
            window = current.get(address)
            if window is None or not same_window(originals[address], window):
                continue
            # Special windows left tiled were not auto-floated by the plugin.
            # Leave them alone rather than force them into an unmanaged canvas.
            if window['workspace']['name'].startswith('special:') and not window['floating']:
                continue
            if not window['floating']:
                commands.append(('setfloating', 'address:'+address))
            commands.extend([('resizewindowpixel', f'exact {width} {height},address:{address}'),
                             ('movewindowpixel', f'exact {x} {y},address:{address}')])
        hc.batch(commands)
        if camera_corrected:
            settle_canvas_camera(hc)
        # polish: leave glass disabled until the leave path has finished rebuilding.
        opened = True
    finally:
        # auto_place resumes immediately; remember_layout stays off until leave.
        if previous:
            # polish: an enter/cleanup failure restores glass but keeps crash evidence.
            cleanup_failed = False
            try:
                restore_option_values(hc, {CANVAS_AUTO_PLACE: previous[CANVAS_AUTO_PLACE]}
                                      if toggle_started else previous)
            except BaseException:
                cleanup_failed = True
                raise
            finally:
                if toggle_started and (not opened or cleanup_failed) and CANVAS_GLASS in previous:
                    restore_glass(hc, previous)


def set_aside(hc, path, why):
    report(f'{why}; snapshot set aside as {path.name}.stale')
    if not hc.dry:
        os.replace(path, str(path)+'.stale')


def execute(hc, action, path):
    journal = Path(str(path)+'.options')
    restored = False
    opening = False
    leave_options = None
    canvas_restored = False
    try:
        count = canvas_count(hc)
        # The marker exists only while a restore runs, so finding it means that restore was killed.
        marker = Path(str(path)+'.restoring')
        if action == 'toggle':
            previous = read_canvas_options(journal) if journal.exists() else None
            interrupted = marker.exists() or previous is not None and ANIMATIONS in previous
            action = 'leave' if count or (path.exists() and interrupted) else 'enter'
        if action == 'enter':
            if count:
                report('canvas already open; entry snapshot kept')
                return
            if path.exists():
                # The canvas closed without this helper, or its restore failed. Replaying it now would
                # undo everything done since and would block this key. `leave` still replays it by hand.
                try:
                    set_aside(hc, path, 'canvas is closed but an old entry snapshot exists')
                finally:
                    restore_canvas_options(hc, journal)
            # polish: also recover a killed enter whose snapshot is missing.
            elif journal.exists() and any(name in (read_canvas_options(journal) or {})
                                          for name in (ANIMATIONS, CANVAS_GLASS)):
                restore_canvas_options(hc, journal)
            saved = snapshot(hc)
            if not hc.dry:
                marker.unlink(missing_ok=True)
            if hc.dry:
                report(f'would save schema 2 snapshot to {path}')
            else:
                save_atomic(path, saved)
            opening = True   # open_canvas handles option cleanup from here onward
            open_canvas(hc, saved, journal)
            return
        saved = None
        if path.exists():
            try:
                saved = json.loads(path.read_text())
                if saved.get('schema') != 2 or saved.get('instance') != hc.instance:
                    raise ValueError('invalid schema or different compositor')
                validate_clients(saved['clients'])
            except (ValueError, KeyError, TypeError, AttributeError) as error:
                # Never let an unusable snapshot keep the canvas open.
                set_aside(hc, path, f'unusable snapshot ({error}); plugin close only')
                saved = None
        def close_canvas(prefix=()):
            hc.batch([*prefix, ('spatialoverview:overview', 'off all')])
            if not hc.dry:
                for _ in range(50):
                    if canvas_count(hc) == 0:
                        break
                    time.sleep(.02)
                else:
                    raise RuntimeError('canvas did not close; snapshot retained')

        class Reopened(RuntimeError):
            pass

        with preserve_cursor(hc) as restore_cursor:
            if saved is not None and not hc.dry:
                marker.touch()   # from here on a killed run leaves windows floating; the next press must finish it
            if saved is not None:
                if count:
                    zoom_to_desktop(hc)
                leave_options = journal_animations(hc, journal)
                hc.keyword(ANIMATIONS, 0)
            else:
                close_canvas()
            if saved is None:
                report('no saved entry snapshot; plugin close only')
                return
            def before_focus():
                if not hc.dry and canvas_count(hc):
                    raise Reopened('canvas reopened during restore; snapshot retained')
                restore_cursor()
            for last in (False, True):
                try:
                    restore = Restore(hc, saved, None if hc.dry else marker)
                    restore.leave = (leave_options, restore_cursor, close_canvas)
                    canvas_restored = restore.run(before_focus) is True
                    break
                except Reopened:
                    # The plugin parks a monitor's canvas under a window made fullscreen inside it and
                    # brings it back when the restore ends that fullscreen. Close it and restore once more.
                    if last:
                        if not hc.dry:
                            marker.unlink(missing_ok=True)
                        raise
                    close_canvas()
                except Exception:
                    if not hc.dry:
                        marker.unlink(missing_ok=True)   # it ran to its end; only a killed restore is retried
                    raise
            if not hc.dry:
                marker.unlink(missing_ok=True)
                restored = True
    except Exception:
        if action == 'enter' and not opening:
            # A crash journal may predate even the snapshot or initial canvas query.
            previous = read_canvas_options(journal)
            if previous:
                restore_option_values(hc, previous)
        raise
    finally:
        if action == 'leave':
            restore_canvas_options(hc, journal, leave_options if hc.dry else None,
                                   canvas_restored=canvas_restored)
    # Option restoration is part of success too; retain the snapshot if it fails.
    if restored:
        path.unlink()


def main(argv):
    if argv and argv[0] == '--replay-restore':
        if len(argv) != 3:
            raise ValueError('usage: phantomat-toggle --replay-restore STATE.json CURRENT.json')
        saved, current = [json.loads(Path(p).read_text()) for p in argv[1:]]
        if isinstance(saved, list):
            saved = dict(clients=saved, monitors=[])
        if isinstance(current, list):
            current = dict(clients=current, monitors=[])

        class Replay(Hyprctl):
            def query(self, name, *args):
                return current.get(name, {} if name in ('activewindow', 'activeworkspace') else [])

        validate_clients(saved['clients'])
        metrics = saved.get('metrics', dict(gaps_in=[0]*4, gaps_out=[0]*4, border=0, groupbar=0))
        saved.setdefault('trees', workspace_trees(saved['clients'], saved.get('monitors', []), metrics))
        restore = Restore(Replay(saved.get('instance', 'offline'), dry=True), saved)
        with preserve_cursor(restore.hc) as restore_cursor:
            restore.placement()
            restore.active_workspaces(before_rebuild=True)
            restore.tiles()
            restore.finish()
            restore_cursor()
            restore.restore_focus()
        return 0
    if len(argv) > 1 or argv and argv[0] not in ('enter', 'leave', 'toggle'):
        raise ValueError('usage: phantomat-toggle [enter|leave|toggle]')
    runtime = Path(os.environ.setdefault('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}'))
    instance = os.environ.get('HYPRLAND_INSTANCE_SIGNATURE', '')
    if not instance:
        candidates = [p for p in (runtime/'hypr').glob('*') if (p/'.socket.sock').exists()]
        if not candidates:
            raise RuntimeError('no compositor instance found in selected runtime directory')
        instance = max(candidates, key=lambda p: p.stat().st_mtime).name
        os.environ['HYPRLAND_INSTANCE_SIGNATURE'] = instance
    hc = Hyprctl(instance, os.environ.get('PHANTOMAT_DRY_RUN') == '1')
    if not re.search(r'^Plugin\s+spatialoverview\s', hc.run('plugins', 'list'), re.M):
        report('spatialoverview is not loaded; nothing to do')
        return 0
    path = runtime/('phantomat-toggle-'+re.sub(r'[^a-zA-Z0-9_.-]', '_', instance)+'.json')
    if hc.dry:
        execute(hc, argv[0] if argv else 'toggle', path)
    else:
        with open(str(path)+'.lock', 'a') as lock:
            deadline = time.monotonic()+8
            while True:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if not argv or argv[0] == 'toggle':
                        # A queued toggle would undo the one still running.
                        report('a toggle is still running; this key press is ignored')
                        return 0
                    if time.monotonic() >= deadline:
                        raise RuntimeError('another invocation is still running')
                    time.sleep(.05)
            execute(hc, argv[0] if argv else 'toggle', path)
    return 0


if __name__ == '__main__':
    os.umask(0o077)
    for number in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
        # Unwind normally so the temporary options and the pointer are put back.
        signal.signal(number, lambda received, _: sys.exit(128+received))
    try:
        sys.exit(main(sys.argv[1:]))
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as error:
        report(str(error))
        notify(str(error))
        sys.exit(1)
