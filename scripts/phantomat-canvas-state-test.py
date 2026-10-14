#!/usr/bin/env python3
"""Offline tests. No test calls hyprctl or requires a compositor."""
import copy
import importlib.util
import pathlib
import contextlib
import io
import json
import tempfile
import unittest
from unittest.mock import patch

PATH = pathlib.Path(__file__).with_name('phantomat-canvas-state.py')
spec = importlib.util.spec_from_file_location('canvas_state', PATH)
state = importlib.util.module_from_spec(spec) if PATH.exists() else None
if state is not None:
    spec.loader.exec_module(state)


def client(address, x, y, w, h, **extra):
    result = dict(address=address, pid=123, stableId=address, mapped=True,
                  workspace=dict(id=1, name='1'), monitor=0, floating=False,
                  pinned=False, fullscreen=0, fullscreenClient=0, grouped=[],
                  hidden=False, at=[x, y], size=[w, h])
    result.update(extra)
    return result


MONITOR = dict(id=0, name='TEST', x=3000, y=420, width=1920, height=1080,
               scale=1, transform=0, reserved=[0, 27, 0, 0], focused=True,
               activeWorkspace=dict(id=1, name='1'), specialWorkspace=dict(id=0, name=''))
METRICS = dict(gaps_out=[8]*4, gaps_in=[18]*4, border=4, groupbar=50)


class Trees(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(state, 'Python restore helper is missing')

    def test_mixed_splits_and_pixel_extents(self):
        tiles = [client('0xa', 12, 12, 600, 1029),
                 client('0xb', 656, 12, 1252, 400),
                 client('0xc', 656, 456, 1252, 585)]
        tree = state.workspace_trees(tiles, [], METRICS)['1']
        self.assertEqual(tree['split'], 'h')
        self.assertEqual(tree['children'][0]['members'], ['0xa'])
        self.assertEqual(tree['children'][1]['split'], 'v')
        self.assertEqual(tree['children'][1]['children'][0]['box'], [656, 12, 1252, 400])
        self.assertEqual(tree['children'][1]['children'][1]['members'], ['0xc'])

    def test_four_windows_keep_two_horizontal_subtrees(self):
        tiles = [client('0xa', 0, 0, 400, 300), client('0xc', 444, 0, 556, 300),
                 client('0xb', 0, 344, 650, 656), client('0xd', 694, 344, 306, 656)]
        tree = state.workspace_trees(tiles, [], METRICS)['1']
        self.assertEqual(tree['split'], 'v')
        self.assertEqual([n['split'] for n in tree['children']], ['h', 'h'])

    def test_group_is_one_tile_and_header_is_not_a_split(self):
        a = client('0xa', 3012, 509, 926, 979, grouped=['0xa', '0xb'])
        b = client('0xb', 3012, 509, 926, 979, grouped=['0xa', '0xb'], hidden=True)
        c = client('0xc', 3982, 459, 926, 1029)
        tree = state.workspace_trees([a, b, c], [MONITOR], METRICS)['1']
        self.assertEqual(tree['children'][0]['members'], ['0xa', '0xb'])
        self.assertEqual(tree['children'][0]['box'], [3012, 459, 926, 1029])
        self.assertEqual(tree['children'][0]['representative'], '0xa')

    def test_fullscreen_hole_uses_peer_and_monitor_insets(self):
        a = client('0xa', 3000, 420, 1920, 1080, fullscreen=2, fullscreenClient=2)
        b = client('0xb', 3982, 459, 926, 1029)
        tree = state.workspace_trees([a, b], [MONITOR], METRICS)['1']
        self.assertEqual(tree['children'][0]['rect'], [3012, 459, 926, 1029])
        self.assertEqual(tree['children'][1]['members'], ['0xb'])

    def test_maximised_hole_on_rotated_scaled_monitor(self):
        m = dict(MONITOR, x=1920, y=0, transform=1)
        a = client('0xa', 1932, 39, 1056, 1869, fullscreen=1, fullscreenClient=1)
        b = client('0xb', 1932, 996, 1056, 912)
        tree = state.workspace_trees([a, b], [m], METRICS)['1']
        self.assertEqual(tree['split'], 'v')
        self.assertEqual(tree['children'][0]['rect'], [1932, 39, 1056, 913])

    def test_fullscreen_hole_respects_monitor_scale(self):
        m = dict(MONITOR, scale=2)
        a = client('0xa', 3000, 420, 960, 540, fullscreen=2, fullscreenClient=2)
        b = client('0xb', 3502, 459, 446, 489)
        tree = state.workspace_trees([a, b], [m], METRICS)['1']
        self.assertEqual(tree['children'][0]['rect'], [3012, 459, 446, 489])

    def test_fullscreen_hole_among_three_peers_is_one_tile(self):
        a = client('0xa', 3000, 420, 1920, 1080, fullscreen=2, fullscreenClient=2)
        b = client('0xb', 3982, 459, 926, 400)
        c = client('0xc', 3012, 903, 926, 585)
        d = client('0xd', 3982, 903, 926, 585)
        tree = state.workspace_trees([a, b, c, d], [MONITOR], METRICS)['1']
        tile = next(n for n in state.leaves(tree) if n['representative'] == '0xa')
        self.assertEqual(tile['rect'], [3012, 459, 926, 400])

    def test_scenario_f_fullscreen_and_maximised_tiles_under_original_geometry(self):
        second = dict(MONITOR, id=1, name='OTHER', x=1920, y=0, transform=1)
        clients = [client('0xa', 3000, 420, 1920, 1080, fullscreen=2, fullscreenClient=2),
                   client('0xb', 3982, 459, 926, 1029),
                   client('0xc', 1932, 39, 1056, 1869, monitor=1,
                          workspace=dict(id=2, name='2'), fullscreen=1, fullscreenClient=1),
                   client('0xe', 1932, 996, 1056, 912, monitor=1, workspace=dict(id=2, name='2'))]
        trees = state.workspace_trees(clients, [MONITOR, second], METRICS)
        self.assertEqual([t['rect'] for t in state.leaves(trees['1'])],
                         [[3012, 459, 926, 1029], [3982, 459, 926, 1029]])
        self.assertEqual([t['rect'] for t in state.leaves(trees['2'])],
                         [[1932, 39, 1056, 913], [1932, 996, 1056, 912]])

    def test_hidden_workspaces_have_independent_trees(self):
        a = client('0xa', 0, 0, 400, 900)
        b = client('0xb', 444, 0, 556, 900)
        c = client('0xc', 0, 0, 600, 900, workspace=dict(id=3, name='3'))
        d = client('0xd', 644, 0, 356, 900, workspace=dict(id=3, name='3'))
        trees = state.workspace_trees([a, b, c, d], [], METRICS)
        self.assertEqual(set(trees), {'1', '3'})
        self.assertEqual(trees['3']['children'][0]['members'], ['0xc'])

    def test_groupbar_disabled_does_not_reserve_space_when_stacked(self):
        a = client('0xa', 0, 0, 400, 900, grouped=['0xa', '0xb'])
        b = dict(a, address='0xb')
        c = client('0xc', 444, 0, 556, 900)
        tree = state.workspace_trees([a, b, c], [], dict(METRICS, groupbar=0,
                                     groupbar_stacked=1, groupbar_member=42, groupbar_upper=8))['1']
        self.assertEqual(tree['children'][0]['box'], [0, 0, 400, 900])

    def test_three_parallel_columns_have_deterministic_binary_tree(self):
        tiles = [client('0xa', 0, 0, 300, 900), client('0xb', 344, 0, 300, 900),
                 client('0xc', 688, 0, 300, 900)]
        tree = state.workspace_trees(tiles, [], METRICS)['1']
        self.assertEqual(tree['children'][0]['members'], ['0xa'])
        self.assertEqual(tree['children'][1]['children'][1]['members'], ['0xc'])

    def test_overlap_fails_before_canvas_mutation(self):
        with self.assertRaises(ValueError):
            state.workspace_trees([client('0xa', 0, 0, 400, 400),
                                   client('0xb', 200, 200, 400, 400)], [], METRICS)

    def test_closed_group_representative_is_replaced(self):
        a = client('0xa', 0, 0, 400, 900, grouped=['0xa', '0xb'])
        b = client('0xb', 0, 0, 400, 900, grouped=['0xa', '0xb'], hidden=True)
        c = client('0xc', 444, 0, 556, 900)
        tree = state.workspace_trees([a, b, c], [], dict(METRICS, groupbar=0))['1']
        pruned = state.prune_tree(tree, {'0xb', '0xc'})
        self.assertEqual(pruned['children'][0]['representative'], '0xb')
        self.assertEqual(pruned['children'][0]['members'], ['0xb'])


class Plans(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(state, 'Python restore helper is missing')
        self.tiles = [client('0xa', 12, 12, 600, 1029),
                      client('0xb', 656, 12, 1252, 400),
                      client('0xc', 656, 456, 1252, 585)]
        self.tree = state.workspace_trees(self.tiles, [], METRICS)['1']

    def test_top_down_rebuild_sets_parent_before_children(self):
        self.assertEqual(state.rebuild_plan(self.tree), [
            ('setfloating', 'address:0xa'), ('setfloating', 'address:0xb'),
            ('setfloating', 'address:0xc'), ('movecursor', '960 526'),
            ('focuswindow', 'address:0xa'), ('settiled', 'address:0xa'),
            ('movecursor', '960 526'), ('focuswindow', 'address:0xa'), ('layoutmsg', 'preselect r'),
            ('settiled', 'address:0xb'), ('resizewindowpixel', 'exact 600 1029,address:0xa'),
            ('movecursor', '1282 526'), ('focuswindow', 'address:0xb'), ('layoutmsg', 'preselect d'),
            ('settiled', 'address:0xc'), ('resizewindowpixel', 'exact 1252 400,address:0xb')])

    def test_four_window_insert_warps_to_each_absolute_node_before_focus(self):
        tiles = [client('0xa', 3012, 459, 400, 300),
                 client('0xc', 3456, 459, 556, 300),
                 client('0xd', 3012, 803, 650, 656),
                 client('0xb', 3706, 803, 306, 656)]
        tree = state.workspace_trees(tiles, [], METRICS)['1']
        commands = state.rebuild_plan(tree)
        splits = [i for i, (name, _) in enumerate(commands) if name == 'layoutmsg']
        self.assertEqual([commands[i-2:i+3] for i in splits], [
            [('movecursor', '3512 959'), ('focuswindow', 'address:0xa'),
             ('layoutmsg', 'preselect d'), ('settiled', 'address:0xd'),
             ('resizewindowpixel', 'exact 1000 300,address:0xa')],
            [('movecursor', '3512 609'), ('focuswindow', 'address:0xa'),
             ('layoutmsg', 'preselect r'), ('settiled', 'address:0xc'),
             ('resizewindowpixel', 'exact 400 300,address:0xa')],
            [('movecursor', '3512 1131'), ('focuswindow', 'address:0xd'),
             ('layoutmsg', 'preselect r'), ('settiled', 'address:0xb'),
             ('resizewindowpixel', 'exact 650 656,address:0xd')]])

    def test_no_hidden_group_member_is_reinserted_as_another_tile(self):
        self.tiles[0]['grouped'] = ['0xa', '0xd']
        d = dict(self.tiles[0], address='0xd', hidden=True)
        tree = state.workspace_trees(self.tiles+[d], [], dict(METRICS, groupbar=0))['1']
        self.assertNotIn(('settiled', 'address:0xd'), state.rebuild_plan(tree))

    def test_closed_leaf_is_never_dispatched(self):
        tree = state.prune_tree(self.tree, {'0xa', '0xc'})
        self.assertFalse(any('0xb' in arg for _, arg in state.rebuild_plan(tree)))

    def test_address_reuse_does_not_restore_an_unrelated_window(self):
        self.assertFalse(state.same_window(self.tiles[0], dict(self.tiles[0], stableId='new')))
        self.assertFalse(state.same_window(self.tiles[0], dict(self.tiles[0], pid=456)))

    def test_batch_workspace_injection_rejected(self):
        bad = copy.deepcopy(self.tiles)
        bad[0]['workspace']['name'] = 'one; dispatch exit'
        with self.assertRaises(ValueError):
            state.validate_clients(bad)

    def test_group_header_is_subtracted_from_subtree_height_during_rebuild(self):
        a = client('0xa', 0, 50, 400, 250, grouped=['0xa', '0xd'])
        d = dict(a, address='0xd', hidden=True)
        b = client('0xb', 444, 0, 556, 300)
        c = client('0xc', 0, 344, 1000, 656)
        tree = state.workspace_trees([a, b, c, d], [], METRICS)['1']
        commands = state.rebuild_plan(tree)
        self.assertIn(('resizewindowpixel', 'exact 1000 250,address:0xa'), commands)
        self.assertIn(('resizewindowpixel', 'exact 400 250,address:0xa'), commands)


class CanvasTargets(unittest.TestCase):
    def setUp(self):
        self.monitors = [dict(copy.deepcopy(MONITOR), name='DP-1'),
                         dict(copy.deepcopy(MONITOR), id=1, name='DP-2', x=1920, y=0,
                              width=1920, height=1080, transform=1,
                              activeWorkspace=dict(id=2, name='2'),
                              specialWorkspace=dict(id=-99, name='special:shown'))]

    def test_visible_boxes_include_every_state_and_pinned_windows(self):
        windows = [client('0xa', 3012, 459, 600, 1029),
                   client('0xb', 1925, 20, 300, 200, floating=True, monitor=1,
                          workspace=dict(id=2, name='2')),
                   client('0xc', 3030, 470, 800, 900, grouped=['0xc', '0xd']),
                   client('0xd', 3030, 470, 800, 900, grouped=['0xc', '0xd'], hidden=True),
                   client('0xe', 3000, 420, 1920, 1080, fullscreen=2),
                   client('0xf', 3012, 459, 1896, 1029, fullscreen=1),
                   client('0x10', 1940, 40, 500, 600, monitor=1,
                          workspace=dict(id=-99, name='special:shown')),
                   client('0x11', 3050, 500, 70, 80, pinned=True,
                          workspace=dict(id=30, name='30')),
                   client('0x12', 0, 0, 10, 10, mapped=False)]
        saved = dict(clients=windows, monitors=self.monitors)
        before = copy.deepcopy(saved)
        self.assertEqual(state.canvas_targets(saved), {
            '0xa': [3012, 459, 600, 1029], '0xb': [1925, 20, 300, 200],
            '0xc': [3030, 470, 800, 900], '0xd': [3030, 470, 800, 900],
            '0xe': [3000, 420, 1920, 1080], '0xf': [3012, 459, 1896, 1029],
            '0x10': [1940, 40, 500, 600], '0x11': [3050, 500, 70, 80]})
        self.assertEqual(saved, before)

    def test_hidden_blocks_sort_workspaces_and_share_one_special_block_per_monitor(self):
        windows = [client('0xa', 3020, 440, 100, 200, workspace=dict(id=5, name='5')),
                   client('0xb', 3010, 430, 100, 200, workspace=dict(id=3, name='3')),
                   client('0xc', 1950, 40, 200, 300, monitor=1, workspace=dict(id=6, name='6')),
                   client('0xd', 1940, 30, 200, 300, monitor=1, workspace=dict(id=4, name='4')),
                   client('0xe', 3040, 460, 100, 200, workspace=dict(id=-90, name='special:a')),
                   client('0xf', 3050, 470, 100, 200, workspace=dict(id=-91, name='special:b')),
                   client('0x10', 1960, 50, 100, 200, monitor=1,
                          workspace=dict(id=-92, name='special:c'))]
        self.assertEqual(state.canvas_targets(dict(clients=windows, monitors=self.monitors)), {
            '0xa': [7244, 440, 100, 200], '0xb': [5122, 430, 100, 200],
            '0xc': [-426, 40, 200, 300], '0xd': [752, 30, 200, 300],
            '0xe': [9376, 460, 100, 200], '0xf': [9386, 470, 100, 200],
            '0x10': [-1604, 50, 100, 200]})

    def test_blocks_skip_monitor_and_previously_placed_block_collisions(self):
        monitors = [dict(copy.deepcopy(MONITOR), id=i, x=x, y=0, width=100, height=100)
                    for i, x in enumerate((1000, 1110, 0))]
        windows = [client(f'0x{i+1:x}', m['x'], 0, 100, 100, monitor=i,
                          workspace=dict(id=i+2, name=str(i+2))) for i, m in enumerate(monitors)]
        targets = state.canvas_targets(dict(monitors=monitors, clients=windows))
        self.assertEqual(targets, {'0x1': [1220, 0, 100, 100],
                                   '0x2': [1330, 0, 100, 100], '0x3': [-110, 0, 100, 100]})
        boxes = [[m['x'], m['y'], 100, 100] for m in monitors] + list(targets.values())
        for i, (x, y, w, h) in enumerate(boxes):
            for xx, yy, ww, hh in boxes[i+1:]:
                self.assertFalse(x < xx+ww and xx < x+w and y < yy+hh and yy < y+h)

    def test_direction_uses_y_when_larger_and_x_on_ties(self):
        for x, y, expected in ((0, 300, [0, -110, 100, 100]),
                               (300, 300, [-110, 0, 100, 100])):
            with self.subTest(other=(x, y)):
                monitors = [dict(copy.deepcopy(MONITOR), x=0, y=0, width=100, height=100),
                            dict(copy.deepcopy(MONITOR), id=1, x=x, y=y, width=100, height=100)]
                self.assertEqual(state.canvas_targets(dict(monitors=monitors, clients=[
                    client('0xa', 0, 0, 100, 100, workspace=dict(id=3, name='3'))])), {'0xa': expected})

    def test_single_scaled_monitor_and_workspace_monitor_fallback(self):
        window = client('0xa', 3010, 430, 100, 200, workspace=dict(id=3, name='3', monitor='TEST'))
        del window['monitor']
        self.assertEqual(state.canvas_targets(dict(clients=[window], monitors=[dict(MONITOR, scale=2)])),
                         {'0xa': [4066, 430, 100, 200]})

    def test_missing_and_degenerate_hidden_boxes_are_skipped(self):
        windows = [client('0xa', 0, 0, 0, 10, workspace=dict(id=3, name='3')),
                   client('0xb', 0, 0, 10, -1, workspace=dict(id=4, name='4')),
                   client('0xc', 0, 0, 10, 10, workspace=dict(id=5, name='5'))]
        del windows[2]['at']
        self.assertEqual(state.canvas_targets(dict(clients=windows, monitors=self.monitors)), {})


class FakeHyprctl:
    """Transport double for errors and lifecycle; it does not simulate dwindle."""
    instance = 'test-instance'
    dry = False

    def __init__(self, clients):
        self.clients = copy.deepcopy(clients)
        self.monitors = [copy.deepcopy(MONITOR)]
        self.active = clients[0]['address'] if clients else None
        self.screens = 1
        self.options = {}
        self.commands = []
        self.fail_insert = False
        self.refuse_focus = False
        self.cursor = dict(x=4173, y=812)
        self.events = []
        self.batches = []
        self.focus_broken = False
        self.poison_repair = None

    def query(self, name, *args, timeout=8):
        self.events.append(('query', name))
        if name == 'cursorpos':
            return copy.deepcopy(self.cursor)
        if name == 'clients':
            return copy.deepcopy(self.clients)
        if name == 'monitors':
            return copy.deepcopy(self.monitors)
        if name == 'workspaces':
            workspaces = {m['activeWorkspace']['id']: dict(m['activeWorkspace'], monitor=m['name'])
                          for m in self.monitors}
            for c in self.clients:
                monitor = next((m['name'] for m in self.monitors if m['id'] == c['monitor']), 'TEST')
                workspaces[c['workspace']['id']] = dict(c['workspace'], monitor=monitor)
            return list(workspaces.values())
        if name == 'activewindow':
            return {} if self.active is None else dict(address=self.active)
        if name == 'activeworkspace':
            return copy.deepcopy(self.monitors[0]['activeWorkspace'])
        if name == 'spatialoverview':
            return dict(screens=[{}]*self.screens)
        if name == 'getoption':
            # polish: existing fixtures have no hyprglass unless explicitly supplied.
            if args[0].startswith('plugin:hyprglass:') and args[0] not in self.options:
                raise RuntimeError('no such option')
            if args[0] == 'plugin:hyprglass:glass_opacity':
                return dict(float=self.options[args[0]])
            return dict(int=self.options.get(args[0], 1))
        raise AssertionError(f'unexpected query {name} {args}')

    def keyword(self, name, value):
        self.options[name] = value

    def batch(self, commands):
        self.batches.append(list(commands))
        for name, arg in commands:
            self.commands.append((name, arg))
            self.events.append((name, arg))
            address = arg.removeprefix('address:')
            window = next((c for c in self.clients if c['address'] == address), None)
            if name == 'keyword':
                option, value = arg.split()
                self.keyword(option, int(value))
            if name == 'movecursor':
                self.cursor = dict(zip(('x', 'y'), map(int, arg.split())))
            if name == 'layoutmsg' and self.fail_insert:
                self.fail_insert = False
                raise RuntimeError('injected insert failure')
            if name in ('setfloating', 'settiled') and window:
                window['floating'] = name == 'setfloating'
            elif name == 'focuswindow' and not (self.refuse_focus or self.focus_broken):
                self.active = address
                if window:
                    for monitor in self.monitors:
                        monitor['focused'] = monitor['id'] == window['monitor']
                        if monitor['focused'] and not window['workspace']['name'].startswith('special:'):
                            monitor['activeWorkspace'] = copy.deepcopy(window['workspace'])
            elif name == 'pin' and window:
                window['pinned'] = not window['pinned']
            elif name == 'fullscreenstate':
                window = next(c for c in self.clients if c['address'] == self.active)
                window['fullscreen'], window['fullscreenClient'] = map(int, arg.split())
            elif name == 'spatialoverview:overview':
                # plugin semantics: on = open; toggle = open with navigation, or (already open,
                # persistent canvas) flip navigation and stay open; off = close
                if arg == 'off all' and self.screens:
                    self.close_canvas()
                self.screens = int(arg == 'on all' or arg == 'toggle all')
            elif name == 'workspace':
                monitor = next(m for m in self.monitors if m['focused'])
                previous = monitor['activeWorkspace']
                target = (dict(id=int(arg), name=arg) if not arg.startswith('name:')
                          else dict(id=-1337, name=arg[5:]))
                monitor['activeWorkspace'] = target
                if previous != target:
                    self.focus_broken = self.poison_repair == (monitor['name'], target['id'])
                    if not any(c['monitor'] == monitor['id'] and c['workspace'] == target for c in self.clients):
                        self.active = None
            elif name == 'togglespecialworkspace':
                monitor = next(m for m in self.monitors if m['focused'])
                monitor['specialWorkspace'] = (dict(id=0, name='')
                    if monitor['specialWorkspace']['name'] == 'special:'+arg
                    else dict(id=-99, name='special:'+arg))
            elif name == 'focusmonitor':
                for monitor in self.monitors:
                    monitor['focused'] = monitor['name'] == arg
            elif name == 'moveworkspacetomonitor':
                ws, target = arg.split()
                destination = next(m for m in self.monitors if m['name'] == target)
                for c in self.clients:
                    if c['workspace']['name'] == ws:
                        c['monitor'] = destination['id']
                for monitor in self.monitors:
                    if monitor['name'] != target and monitor['activeWorkspace']['name'] == ws:
                        monitor['activeWorkspace'] = dict(id=99, name='99')
            elif name == 'movetoworkspacesilent':
                target, address = arg.split(',address:')
                window = next(c for c in self.clients if c['address'] == address)
                window['workspace'] = (dict(id=int(target), name=target) if not target.startswith('name:')
                                       else dict(id=-1337, name=target[5:]))

    def close_canvas(self):
        pass


def packet(clients):
    return dict(schema=2, instance='test-instance', clients=copy.deepcopy(clients),
                monitors=[copy.deepcopy(MONITOR)], activewindow=dict(address=clients[0]['address']),
                activeworkspace=dict(id=1, name='1'), metrics=METRICS,
                trees=state.workspace_trees(clients, [MONITOR], METRICS))


class Lifecycle(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(state, 'Python restore helper is missing')
        self.clients = [client('0xa', 3012, 459, 600, 1029),
                        client('0xb', 3656, 459, 1252, 1029)]

    def test_empty_monitor_repair_revives_before_any_rebuild_focus(self):
        hc = FakeHyprctl(self.clients)
        saved = packet(self.clients)
        empty = dict(MONITOR, id=1, name='EMPTY', focused=False,
                     activeWorkspace=dict(id=2, name='2'))
        saved['monitors'].append(copy.deepcopy(empty))
        hc.monitors.append(dict(empty, activeWorkspace=dict(id=9, name='9')))
        hc.poison_repair = ('EMPTY', 2)
        hc.clients[0]['size'][0] += 1
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError, '0 px'):
                state.Restore(hc, saved).run()
        repair = [('focusmonitor', 'EMPTY'), ('workspace', '2'),
                  ('focusmonitor', 'TEST'), ('workspace', '109'), ('workspace', '1')]
        self.assertIn(repair, hc.batches)
        self.assertLess(hc.commands.index(('workspace', '1')),
                        hc.commands.index(('setfloating', 'address:0xa')))
        self.assertFalse(hc.focus_broken)
        self.assertEqual(hc.active, '0xa')
        self.assertEqual([m['activeWorkspace']['id'] for m in hc.monitors], [1, 2])
        self.assertNotIn(109, [ws['id'] for ws in hc.query('workspaces')])

    def test_failed_focus_revives_target_monitor_current_workspace_then_retries(self):
        target = client('0xc', 0, 0, 600, 900, monitor=1, workspace=dict(id=2, name='2'))
        hc = FakeHyprctl(self.clients+[target])
        hc.monitors.append(dict(MONITOR, id=1, name='OTHER', focused=False,
                                activeWorkspace=dict(id=4, name='4')))
        hc.focus_broken = True
        state.Restore(hc, packet(self.clients+[target])).focus(target)
        self.assertEqual(hc.active, '0xc')
        self.assertIn([('focusmonitor', 'OTHER'), ('workspace', '104'), ('workspace', '4')], hc.batches)
        self.assertEqual(sum(name == 'focuswindow' for name, _ in hc.commands), 2)
        self.assertTrue(hc.monitors[1]['focused'])
        self.assertEqual(hc.monitors[1]['activeWorkspace']['id'], 2)
        self.assertNotIn(104, [ws['id'] for ws in hc.query('workspaces')])

    def test_checked_rebuild_self_heals_before_preselect(self):
        hc = FakeHyprctl(self.clients)
        hc.active = None
        hc.focus_broken = True
        saved = packet(self.clients)
        hc.clients[0].update(at=[3999, 888], size=[400, 300], floating=True)
        restore = state.Restore(hc, saved)
        restore.checked_commands(state.rebuild_plan(saved['trees']['1']))
        preselect = hc.commands.index(('layoutmsg', 'preselect r'))
        self.assertLess(hc.commands.index(('workspace', '1')), preselect)
        retry = [i for i, cmd in enumerate(hc.commands) if cmd == ('focuswindow', 'address:0xa')][1]
        self.assertEqual(hc.commands[retry-1], ('movecursor', '3960 973'))
        self.assertFalse(hc.focus_broken)
        self.assertTrue(all(not c['floating'] for c in hc.clients))

    def test_focus_revive_scratch_avoids_saved_live_and_hidden_workspaces(self):
        hc = FakeHyprctl(self.clients)
        saved = packet(self.clients)
        saved['monitors'].append(dict(MONITOR, id=2, name='DISCONNECTED', focused=False,
                                      activeWorkspace=dict(id=1000, name='1000')))
        base_query = hc.query

        def query(name, *args):
            result = base_query(name, *args)
            return result+[dict(id=900, name='900', monitor='TEST')] if name == 'workspaces' else result
        hc.query = query
        hc.active = None
        hc.focus_broken = True
        state.Restore(hc, saved).focus(self.clients[0])
        self.assertIn(('workspace', '1100'), hc.commands)
        self.assertEqual(hc.active, '0xa')
        self.assertEqual(hc.monitors[0]['activeWorkspace'], dict(id=1, name='1'))
        self.assertNotIn(1100, [ws['id'] for ws in hc.query('workspaces')])

    def test_focus_revive_returns_to_named_workspace(self):
        target = dict(self.clients[0], workspace=dict(id=-1337, name='desk'))
        hc = FakeHyprctl([target])
        hc.monitors[0]['activeWorkspace'] = copy.deepcopy(target['workspace'])
        saved = packet([target])
        saved['monitors'] = copy.deepcopy(hc.monitors)
        hc.active = None
        hc.focus_broken = True
        state.Restore(hc, saved).focus(target)
        self.assertEqual(hc.active, '0xa')
        self.assertIn(('workspace', 'name:desk'), hc.commands)
        self.assertEqual(hc.monitors[0]['activeWorkspace'], target['workspace'])

    def test_multiple_monitor_repairs_share_one_batch_and_one_revive(self):
        hc = FakeHyprctl(self.clients)
        saved = packet(self.clients)
        for ident, name, target, current in [(1, 'EMPTY', 2, 9), (2, 'THIRD', 3, 10)]:
            monitor = dict(MONITOR, id=ident, name=name, focused=False,
                           activeWorkspace=dict(id=target, name=str(target)))
            saved['monitors'].append(copy.deepcopy(monitor))
            hc.monitors.append(dict(monitor, activeWorkspace=dict(id=current, name=str(current))))
        state.Restore(hc, saved).run()
        self.assertIn([('focusmonitor', 'EMPTY'), ('workspace', '2'),
                       ('focusmonitor', 'THIRD'), ('workspace', '3'),
                       ('focusmonitor', 'TEST'), ('workspace', '110'), ('workspace', '1')], hc.batches)
        self.assertEqual(sum(cmd == ('workspace', '110') for cmd in hc.commands), 1)
        self.assertEqual([m['activeWorkspace']['id'] for m in hc.monitors], [1, 2, 3])
        self.assertTrue(hc.monitors[0]['focused'])
        self.assertEqual(hc.active, '0xa')
        self.assertNotIn(110, [ws['id'] for ws in hc.query('workspaces')])

    def test_late_empty_monitor_repair_revives_before_final_focus(self):
        hc = FakeHyprctl(self.clients)
        saved = packet(self.clients)
        empty = dict(MONITOR, id=1, name='EMPTY', focused=False,
                     activeWorkspace=dict(id=2, name='2'))
        saved['monitors'].append(copy.deepcopy(empty))
        hc.monitors.append(dict(empty, activeWorkspace=dict(id=4, name='4')))
        hc.poison_repair = ('EMPTY', 2)
        hc.active = '0xb'
        restore = state.Restore(hc, saved)
        restore.finish()
        restore.restore_focus()
        self.assertEqual(hc.active, '0xa')
        self.assertFalse(hc.focus_broken)
        self.assertLess(hc.commands.index(('workspace', '1')),
                        hc.commands.index(('focuswindow', 'address:0xa')))
        self.assertEqual([m['activeWorkspace']['id'] for m in hc.monitors], [1, 2])

    def test_revive_rejects_scratch_workspace_that_survives_leave(self):
        hc = FakeHyprctl(self.clients)
        base_query = hc.query

        def query(name, *args):
            result = base_query(name, *args)
            if name == 'workspaces' and ('workspace', '101') in hc.commands:
                result.append(dict(id=101, name='101', monitor='TEST'))
            return result
        hc.query = query
        hc.active = None
        hc.refuse_focus = True
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError, 'scratch workspace 101 survived'):
                state.Restore(hc, packet(self.clients)).focus(self.clients[0])
        self.assertEqual(hc.monitors[0]['activeWorkspace']['id'], 1)
        self.assertTrue(hc.monitors[0]['focused'])
        self.assertEqual(sum(name == 'focuswindow' for name, _ in hc.commands), 1)

    def test_revive_rejects_return_on_wrong_monitor_before_retry(self):
        hc = FakeHyprctl(self.clients)
        hc.monitors.append(dict(MONITOR, id=1, name='OTHER', focused=False,
                                activeWorkspace=dict(id=2, name='2')))
        base_batch = hc.batch

        def batch(commands):
            base_batch(commands)
            if ('workspace', '102') in commands:
                hc.monitors[0]['focused'] = False
                hc.monitors[1]['focused'] = True
        hc.batch = batch
        hc.active = None
        hc.refuse_focus = True
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError, 'revive did not return to monitor TEST'):
                state.Restore(hc, packet(self.clients)).focus(self.clients[0])
        self.assertEqual(sum(name == 'focuswindow' for name, _ in hc.commands), 1)

    def test_revive_preserves_special_workspace_if_workspace_switch_closes_it(self):
        hc = FakeHyprctl(self.clients)
        hc.monitors[0]['specialWorkspace'] = dict(id=-99, name='special:stash')
        saved = packet(self.clients)
        saved['monitors'] = copy.deepcopy(hc.monitors)
        base_batch = hc.batch

        def batch(commands):
            base_batch(commands)
            if ('workspace', '101') in commands:
                hc.monitors[0]['specialWorkspace'] = dict(id=0, name='')
        hc.batch = batch
        hc.active = None
        hc.focus_broken = True
        state.Restore(hc, saved).focus(self.clients[0])
        self.assertEqual(hc.monitors[0]['specialWorkspace'], dict(id=-99, name='special:stash'))
        self.assertTrue(hc.monitors[0]['focused'])
        self.assertEqual(hc.monitors[0]['activeWorkspace']['id'], 1)
        self.assertEqual(hc.active, '0xa')

    def test_focus_warps_to_live_target_instead_of_stale_saved_rect(self):
        hc = FakeHyprctl(self.clients)
        hc.clients[0].update(at=[-1200, 200], size=[800, 400])
        hc.active = '0xb'
        base_batch = hc.batch

        def batch(commands):
            for name, arg in commands:
                if name == 'focuswindow':
                    hc.refuse_focus = hc.cursor != dict(x=-800, y=400)
                base_batch([(name, arg)])
        hc.batch = batch
        state.Restore(hc, packet(self.clients)).focus(self.clients[0])
        self.assertEqual(hc.active, '0xa')
        self.assertEqual(hc.commands[:2], [('movecursor', '-800 400'),
                                         ('focuswindow', 'address:0xa')])

    def test_checked_rebuild_keeps_node_cursor_before_preselect(self):
        hc = FakeHyprctl(self.clients)
        hc.clients[0].update(at=[3999, 888], size=[400, 300], floating=True)
        restore = state.Restore(hc, packet(self.clients))
        restore.checked_commands(state.rebuild_plan(restore.saved['trees']['1']))
        split = hc.commands.index(('layoutmsg', 'preselect r'))
        self.assertEqual(hc.commands[split-2:split], [('movecursor', '3960 973'),
                                                   ('focuswindow', 'address:0xa')])

    def test_leave_saves_pointer_before_plugin_close_and_restores_it_after_final_focus(self):
        hc = FakeHyprctl(self.clients)
        hc.active = '0xb'  # Require a focus change; already-correct focus is now skipped.
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory)/'snapshot.json'
            path.write_text(json.dumps(packet(self.clients)))
            state.execute(hc, 'leave', path)
        self.assertLess(hc.events.index(('query', 'cursorpos')),
                        hc.events.index(('spatialoverview:overview', 'off all')))
        self.assertEqual(hc.commands[-2:], [('focuswindow', 'address:0xa'),
                                          ('movecursor', '4173 812')])
        self.assertEqual(hc.cursor, dict(x=4173, y=812))

    def test_failed_leave_still_restores_pointer_and_keeps_snapshot(self):
        hc = FakeHyprctl(self.clients)
        hc.clients[0]['size'][0] += 1
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stderr(io.StringIO()):
            path = pathlib.Path(directory)/'snapshot.json'
            path.write_text(json.dumps(packet(self.clients)))
            with self.assertRaises(RuntimeError):
                state.execute(hc, 'leave', path)
            self.assertTrue(path.exists())
        self.assertEqual(hc.commands[-1], ('movecursor', '4173 812'))
        self.assertEqual(hc.active, '0xa')  # Rebuild already focused the saved window.
        self.assertEqual(hc.cursor, dict(x=4173, y=812))

    def test_pointer_restore_is_best_effort_after_success(self):
        hc = FakeHyprctl(self.clients)
        base_batch = hc.batch

        def batch(commands):
            if len(commands) > 1 and ('movecursor', '4173 812') in commands:
                base_batch(commands[:-1])
                raise RuntimeError('pointer warp refused')
            if commands == [('movecursor', '4173 812')]:
                raise RuntimeError('pointer warp refused')
            base_batch(commands)
        hc.batch = batch
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stderr(io.StringIO()) as stderr:
            path = pathlib.Path(directory)/'snapshot.json'
            path.write_text(json.dumps(packet(self.clients)))
            state.execute(hc, 'leave', path)
            self.assertFalse(path.exists())
        self.assertIn('pointer warp refused', stderr.getvalue())

    def test_ten_tiles_restore_pointer_before_final_focus_including_revive_retry(self):
        clients = [client(f'0x{index+1:x}', 3012+index*188, 459, 144, 1029)
                   for index in range(10)]
        for break_focus in (False, True):
            with self.subTest(revive_retry=break_focus):
                hc = FakeHyprctl(clients)
                hc.active = clients[-1]['address']
                hc.cursor = dict(x=3272, y=973)  # Over the second tile, not the focused tenth.
                saved = packet(clients)
                saved['activewindow'] = dict(address='0xa')
                base_batch = hc.batch

                def batch(commands):
                    for name, arg in commands:
                        base_batch([(name, arg)])
                        if name == 'movecursor':
                            x, y = hc.cursor['x'], hc.cursor['y']
                            window = next((c for c in hc.clients
                                           if c['at'][0] <= x < c['at'][0]+c['size'][0]
                                           and c['at'][1] <= y < c['at'][1]+c['size'][1]), None)
                            if window:
                                hc.active = window['address']
                            if arg == '3272 973':
                                hc.focus_broken = break_focus
                hc.batch = batch
                with tempfile.TemporaryDirectory() as directory:
                    path = pathlib.Path(directory)/'snapshot.json'
                    path.write_text(json.dumps(saved))
                    state.execute(hc, 'leave', path)
                    self.assertFalse(path.exists())
                self.assertEqual(hc.active, '0xa')
                self.assertEqual(hc.cursor, dict(x=3272, y=973))
                last_warp = max(i for i, (name, _) in enumerate(hc.commands) if name == 'movecursor')
                self.assertEqual(hc.commands[last_warp], ('movecursor', '3272 973'))
                self.assertEqual(hc.commands[-1], ('focuswindow', 'address:0xa'))
                self.assertEqual(hc.events[-1], ('query', 'activewindow'))
                self.assertEqual(sum(name == 'focuswindow' for name, _ in hc.commands[last_warp+1:]),
                                 2 if break_focus else 1)

    def test_focus_overridden_after_final_focus_is_reported_and_keeps_snapshot(self):
        hc = FakeHyprctl(self.clients)
        hc.active = '0xb'  # Exercise an actual final focus dispatch.
        base_query = hc.query

        def query(name, *args):
            if name == 'clients' and hc.commands and hc.commands[-1] in (
                    ('focuswindow', 'address:0xa'), ('movecursor', '4173 812')):
                hc.active = '0xb'
            return base_query(name, *args)
        hc.query = query
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stderr(io.StringIO()) as stderr:
            path = pathlib.Path(directory)/'snapshot.json'
            path.write_text(json.dumps(packet(self.clients)))
            with self.assertRaisesRegex(RuntimeError, 'state verification'):
                state.execute(hc, 'leave', path)
            self.assertTrue(path.exists())
        self.assertIn('focused window differs', stderr.getvalue())

    def test_leave_with_closed_tenth_and_new_tile_removes_snapshot(self):
        clients = [client(f'0x{index+1:x}', 3012+index*188, 459, 144, 1029)
                   for index in range(10)]
        saved = packet(clients)
        saved['activewindow'] = dict(address='0xa')
        hc = FakeHyprctl(clients[:-1]+[client('0xb', 4800, 700, 144, 788)])
        hc.clients[7].update(at=[4328, 459], size=[144, 480])
        hc.clients[8].update(at=[4516, 459], size=[144, 480])
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stderr(io.StringIO()) as stderr:
            path = pathlib.Path(directory)/'snapshot.json'
            path.write_text(json.dumps(saved))
            state.execute(hc, 'leave', path)
            self.assertFalse(path.exists())
        self.assertTrue(all(not c['floating'] for c in hc.clients))
        self.assertIn('windows opened/closed', stderr.getvalue())
        self.assertNotIn('state verification failed', stderr.getvalue())

    def test_churn_keeps_geometry_strict_on_other_workspaces_and_floating_windows(self):
        other = client('0xc', 3012, 459, 1896, 1029, workspace=dict(id=2, name='2'))
        floating = client('0xd', 3100, 500, 300, 200, floating=True)
        saved = packet(self.clients+[other, floating])
        for address, field in (('0xc', 'size'), ('0xc', 'at'), ('0xd', 'size'), ('0xd', 'at')):
            with self.subTest(address=address, field=field):
                hc = FakeHyprctl(saved['clients']+[client('0xe', 0, 0, 300, 500)])
                hc.clients[0]['size'][0] -= 10
                target = next(c for c in hc.clients if c['address'] == address)
                target[field][0] += 1
                with contextlib.redirect_stderr(io.StringIO()) as stderr:
                    with self.assertRaisesRegex(RuntimeError, 'state verification'):
                        state.Restore(hc, saved).verify()
                self.assertIn(f'{address} {field}:', stderr.getvalue())
                self.assertNotIn('0xa size:', stderr.getvalue())

    def test_new_floating_window_does_not_waive_tiled_geometry(self):
        hc = FakeHyprctl(self.clients+[client('0xc', 0, 0, 300, 500, floating=True)])
        hc.clients[0]['size'][0] -= 1
        with contextlib.redirect_stderr(io.StringIO()) as stderr:
            with self.assertRaisesRegex(RuntimeError, 'state verification'):
                state.Restore(hc, packet(self.clients)).verify()
        self.assertIn('0xa size:', stderr.getvalue())

    def test_churn_still_rejects_survivor_state_mismatches(self):
        for field, value in (('workspace', dict(id=2, name='2')), ('monitor', 1),
                             ('floating', True), ('pinned', True), ('fullscreen', 1), ('fullscreenClient', 1)):
            with self.subTest(field=field):
                hc = FakeHyprctl(self.clients+[client('0xc', 0, 0, 300, 500)])
                hc.clients[0][field] = value
                with contextlib.redirect_stderr(io.StringIO()) as stderr:
                    with self.assertRaisesRegex(RuntimeError, 'state verification'):
                        state.Restore(hc, packet(self.clients)).verify()
                self.assertIn(f'0xa {field}:', stderr.getvalue())

    def test_churn_failures_keep_snapshot_for_dispatch_placement_and_unaffected_geometry(self):
        other = client('0xd', 3012, 459, 1896, 1029, workspace=dict(id=2, name='2'))
        saved = packet(self.clients+[other])
        for failure in ('dispatch', 'workspace', 'monitor', 'unaffected geometry'):
            with self.subTest(failure=failure):
                hc = FakeHyprctl(saved['clients']+[client('0xc', 3000, 700, 300, 200)])
                hc.clients[0]['size'][0] -= 10
                if failure == 'dispatch':
                    hc.fail_insert = True
                elif failure == 'unaffected geometry':
                    hc.clients[2]['size'][0] -= 1
                else:
                    base_batch = hc.batch

                    def batch(commands):
                        base_batch(commands)
                        if ('movecursor', '4173 812') in commands:
                            hc.clients[1][failure] = dict(id=2, name='2') if failure == 'workspace' else 1
                    hc.batch = batch
                with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stderr(io.StringIO()):
                    path = pathlib.Path(directory)/'snapshot.json'
                    original = json.dumps(saved)
                    path.write_text(original)
                    with self.assertRaises(RuntimeError):
                        state.execute(hc, 'leave', path)
                    self.assertEqual(path.read_text(), original)

    def test_fullscreen_retiles_and_verifies_before_both_mode_values(self):
        for modes in ([2, 2], [1, 1], [2, 1]):
            with self.subTest(modes=modes):
                hc = FakeHyprctl(self.clients)
                hc.clients[0]['floating'] = True
                restore = state.Restore(hc, packet(self.clients))
                restore.fullscreen(self.clients[0], modes)
                self.assertFalse(hc.clients[0]['floating'])
                self.assertEqual([hc.clients[0]['fullscreen'], hc.clients[0]['fullscreenClient']], modes)
                tile = hc.events.index(('settiled', 'address:0xa'))
                fullscreen = hc.events.index(('fullscreenstate', f'{modes[0]} {modes[1]}'))
                self.assertIn(('query', 'clients'), hc.events[tile+1:fullscreen])
                self.assertEqual(hc.events[fullscreen-3:fullscreen], [
                    ('movecursor', '3312 973'), ('focuswindow', 'address:0xa'),
                    ('query', 'activewindow')])

    def test_fullscreen_does_not_dispatch_if_tiling_was_refused(self):
        hc = FakeHyprctl(self.clients)
        hc.clients[0]['floating'] = True
        base_batch = hc.batch

        def batch(commands):
            base_batch(commands)
            if ('settiled', 'address:0xa') in commands:
                hc.clients[0]['floating'] = True
        hc.batch = batch
        with self.assertRaisesRegex(RuntimeError, 'tiled'):
            state.Restore(hc, packet(self.clients)).fullscreen(self.clients[0], [2, 2])
        self.assertFalse(any(name == 'fullscreenstate' for name, _ in hc.commands))

    def test_fullscreen_checks_client_and_internal_state_after_dispatch(self):
        hc = FakeHyprctl(self.clients)
        base_batch = hc.batch

        def batch(commands):
            base_batch(commands)
            if any(name == 'fullscreenstate' for name, _ in commands):
                hc.clients[0]['fullscreenClient'] = 0
        hc.batch = batch
        with self.assertRaisesRegex(RuntimeError, 'fullscreen'):
            state.Restore(hc, packet(self.clients)).fullscreen(self.clients[0], [2, 2])

    def test_fullscreen_workspace_is_rebuilt_even_when_native_tiles_match(self):
        saved = packet(self.clients)
        saved['clients'][0].update(fullscreen=2, fullscreenClient=2,
                                   at=[3000, 420], size=[1920, 1080])
        hc = FakeHyprctl(self.clients)
        with contextlib.redirect_stderr(io.StringIO()):
            state.Restore(hc, saved).rebuild_workspace('1', saved['trees']['1'])
        self.assertIn(('layoutmsg', 'preselect r'), hc.commands)
        self.assertTrue(all(not c['floating'] for c in hc.clients))

    def test_cursor_capture_unavailable_does_not_prevent_layout_restore(self):
        hc = FakeHyprctl(self.clients)
        base_query = hc.query

        def query(name, *args):
            if name == 'cursorpos':
                raise RuntimeError('cursorpos unavailable')
            return base_query(name, *args)
        hc.query = query
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stderr(io.StringIO()) as stderr:
            path = pathlib.Path(directory)/'snapshot.json'
            path.write_text(json.dumps(packet(self.clients)))
            state.execute(hc, 'leave', path)
            self.assertFalse(path.exists())
        self.assertIn('cursorpos unavailable', stderr.getvalue())
        self.assertEqual(hc.active, '0xa')

    def test_plugin_close_failure_still_restores_pointer(self):
        hc = FakeHyprctl(self.clients)
        base_batch = hc.batch

        def batch(commands):
            base_batch(commands)
            if ('spatialoverview:overview', 'off all') in commands:
                hc.cursor = dict(x=0, y=0)
                raise RuntimeError('plugin close failed')
        hc.batch = batch
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory)/'snapshot.json'
            path.write_text(json.dumps(packet(self.clients)))
            with self.assertRaisesRegex(RuntimeError, 'plugin close failed'):
                state.execute(hc, 'leave', path)
            self.assertTrue(path.exists())
        self.assertEqual(hc.commands[-1], ('movecursor', '4173 812'))
        self.assertEqual(hc.cursor, dict(x=4173, y=812))

    def test_rebuild_clears_remaining_fullscreen_before_floating_tiles(self):
        saved = packet(self.clients)
        saved['clients'][0].update(fullscreen=2, fullscreenClient=2,
                                   at=[3000, 420], size=[1920, 1080])
        hc = FakeHyprctl(saved['clients'])
        base_batch = hc.batch

        def batch(commands):
            base_batch(commands)
            if ('fullscreenstate', '0 0') in commands:
                hc.clients[0].update(at=[3012, 459], size=[600, 1029])
        hc.batch = batch
        with contextlib.redirect_stderr(io.StringIO()):
            state.Restore(hc, saved).rebuild_workspace('1', saved['trees']['1'])
        clear = hc.commands.index(('fullscreenstate', '0 0'))
        self.assertLess(clear, hc.commands.index(('setfloating', 'address:0xa')))
        self.assertEqual(hc.commands[clear-2:clear], [('movecursor', '3960 960'),
                                                   ('focuswindow', 'address:0xa')])

    def test_offline_replay_shows_fullscreen_retile_and_cursor_restore(self):
        saved = packet(self.clients)
        saved['clients'][0].update(fullscreen=2, fullscreenClient=2,
                                   at=[3000, 420], size=[1920, 1080])
        current = dict(clients=[dict(c, floating=True) for c in self.clients],
                       monitors=[MONITOR], cursorpos=dict(x=4173, y=812))
        with tempfile.TemporaryDirectory() as directory:
            saved_path = pathlib.Path(directory)/'saved.json'
            current_path = pathlib.Path(directory)/'current.json'
            saved_path.write_text(json.dumps(saved))
            current_path.write_text(json.dumps(current))
            with patch.object(state.subprocess, 'run', side_effect=AssertionError('live transport invoked')):
                with contextlib.redirect_stdout(io.StringIO()) as output, contextlib.redirect_stderr(io.StringIO()) as stderr:
                    state.main(['--replay-restore', str(saved_path), str(current_path)])
        self.assertIn('dispatch fullscreenstate 2 2', output.getvalue())
        self.assertNotIn('must be tiled', stderr.getvalue())
        self.assertTrue(output.getvalue().splitlines()[-2].endswith("'dispatch movecursor 4173 812'"))
        self.assertTrue(output.getvalue().splitlines()[-1].endswith("'dispatch focuswindow address:0xa'"))

    def test_successful_leave_removes_snapshot(self):
        hc = FakeHyprctl(self.clients)
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory)/'snapshot.json'
            path.write_text(json.dumps(packet(self.clients)))
            state.execute(hc, 'leave', path)
            self.assertFalse(path.exists())
            self.assertEqual(hc.screens, 0)
            self.assertEqual(hc.active, '0xa')

    def test_zero_pixel_failure_retains_snapshot_and_retiles_survivors(self):
        hc = FakeHyprctl(self.clients)
        hc.clients[0]['size'][0] += 1
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stderr(io.StringIO()) as stderr:
            path = pathlib.Path(directory)/'snapshot.json'
            before = json.dumps(packet(self.clients))
            path.write_text(before)
            with self.assertRaisesRegex(RuntimeError, '0 px'):
                state.execute(hc, 'leave', path)
            self.assertEqual(path.read_text(), before)
            self.assertTrue(all(not c['floating'] for c in hc.clients))
            self.assertIn('tile', stderr.getvalue())
            self.assertTrue(all(v == 1 for v in hc.options.values()))

    def test_mid_rebuild_dispatch_failure_retiles_windows_and_restores_options(self):
        hc = FakeHyprctl(self.clients)
        hc.clients[0]['size'][0] += 1
        hc.fail_insert = True
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError, 'injected insert failure'):
                state.Restore(hc, packet(self.clients)).run()
        self.assertTrue(all(not c['floating'] for c in hc.clients))
        self.assertTrue(all(v == 1 for v in hc.options.values()))

    def test_mid_rebuild_failure_retiles_temporarily_detached_new_windows(self):
        hc = FakeHyprctl(self.clients+[client('0xc', 3012, 459, 300, 500)])
        hc.clients[0]['size'][0] += 1
        hc.fail_insert = True
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError, 'injected insert failure'):
                state.Restore(hc, packet(self.clients)).run()
        self.assertTrue(all(not c['floating'] for c in hc.clients))

    def test_failed_focus_is_retried_once_and_reported(self):
        hc = FakeHyprctl(self.clients)
        hc.active = None
        hc.refuse_focus = True
        with contextlib.redirect_stderr(io.StringIO()) as stderr, self.assertRaisesRegex(RuntimeError, 'focus did not reach'):
            state.Restore(hc, packet(self.clients)).focus(self.clients[0])
        self.assertEqual(sum(name == 'focuswindow' for name, _ in hc.commands), 2)
        self.assertIn([('focusmonitor', 'TEST'), ('workspace', '101'), ('workspace', '1')], hc.batches)
        self.assertIn('activewindow={}', stderr.getvalue())
        self.assertIn('monitors=', stderr.getvalue())

    def test_toggle_with_canvas_closed_sets_old_snapshot_aside_and_enters(self):
        # A snapshot left by a canvas that closed without the helper (or by a failed restore)
        # must not be replayed by the next key press, nor block it.
        hc = FakeHyprctl(self.clients)
        hc.screens = 0
        hc.clients[0]['size'][0] += 1
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stderr(io.StringIO()):
            path = pathlib.Path(directory)/'snapshot.json'
            path.write_text('old evidence')
            state.execute(hc, 'toggle', path)
            self.assertEqual(hc.batches[0], [('spatialoverview:overview', 'toggle all')])   # opens with navigation
            self.assertEqual(pathlib.Path(str(path)+'.stale').read_text(), 'old evidence')
            self.assertEqual(json.loads(path.read_text())['clients'][0]['size'][0], 601)

    def test_toggle_retries_a_restore_that_was_killed(self):
        hc = FakeHyprctl(self.clients)
        hc.screens = 0
        hc.options['dwindle:smart_resizing'] = 0          # left forced by the killed run
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stderr(io.StringIO()):
            path = pathlib.Path(directory)/'snapshot.json'
            marker = pathlib.Path(str(path)+'.restoring')
            path.write_text(json.dumps(packet(self.clients)))
            marker.write_text(json.dumps({'dwindle:smart_resizing': 1}))
            state.execute(hc, 'toggle', path)
            self.assertFalse([c for c in hc.commands if c[0] == 'spatialoverview:overview' and c[1] != 'off all'])
            self.assertFalse(path.exists())
            self.assertFalse(marker.exists())
            self.assertEqual(hc.options['dwindle:smart_resizing'], 1)

    def test_failed_restore_keeps_snapshot_but_not_the_retry_marker(self):
        hc = FakeHyprctl(self.clients)
        hc.clients[0]['size'][0] += 1
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stderr(io.StringIO()):
            path = pathlib.Path(directory)/'snapshot.json'
            path.write_text(json.dumps(packet(self.clients)))
            with self.assertRaises(RuntimeError):
                state.execute(hc, 'leave', path)
            self.assertTrue(path.exists())
            self.assertFalse(pathlib.Path(str(path)+'.restoring').exists())

    def test_unusable_snapshot_never_keeps_the_canvas_open(self):
        hc = FakeHyprctl(self.clients)
        saved = dict(packet(self.clients), instance='another-instance')
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stderr(io.StringIO()) as stderr:
            path = pathlib.Path(directory)/'snapshot.json'
            path.write_text(json.dumps(saved))
            state.execute(hc, 'leave', path)
            self.assertEqual(hc.commands, [('spatialoverview:overview', 'off all'), ('movecursor', '4173 812')])
            self.assertFalse(path.exists())
            self.assertTrue(pathlib.Path(str(path)+'.stale').exists())
            self.assertIn('different compositor', stderr.getvalue())

    def test_canvas_reopened_by_the_restore_is_closed_and_restored_once_more(self):
        class Reopening(FakeHyprctl):
            asked = 0

            def query(self, name, *args):
                if name == 'spatialoverview':
                    self.asked += 1
                    if self.asked == 3:               # the query after the atomic restore, after the zoom query
                        self.screens = 1
                return super().query(name, *args)

        hc = Reopening(self.clients)
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stderr(io.StringIO()):
            path = pathlib.Path(directory)/'snapshot.json'
            path.write_text(json.dumps(packet(self.clients)))
            state.execute(hc, 'leave', path)
            self.assertEqual(hc.commands.count(('spatialoverview:overview', 'off all')), 2)
            self.assertEqual(hc.screens, 0)
            self.assertFalse(path.exists())
            self.assertFalse(pathlib.Path(str(path)+'.restoring').exists())

    def test_group_active_tab_is_refocused_and_verified(self):
        a = client('0xa', 3012, 509, 600, 979, grouped=['0xa', '0xb'], acceptsInput=False)
        b = dict(a, address='0xb', stableId='0xb', acceptsInput=True)
        c = client('0xc', 3656, 459, 1252, 1029, acceptsInput=True)
        saved = dict(packet([a, b, c]), activewindow=dict(address='0xc'))
        now = [dict(a, acceptsInput=True), dict(b, acceptsInput=False), c]
        hc = FakeHyprctl(now)
        with contextlib.redirect_stderr(io.StringIO()) as stderr, self.assertRaises(RuntimeError):
            state.Restore(hc, saved).verify()
        self.assertIn('0xb is no longer the active tab', stderr.getvalue())
        hc = FakeHyprctl(now)
        with contextlib.redirect_stderr(io.StringIO()):
            state.Restore(hc, saved).finish()
        self.assertIn(('focuswindow', 'address:0xb'), hc.commands)

    def test_pointer_on_another_monitor_is_put_back_and_not_a_failure(self):
        other = dict(MONITOR, id=1, name='OTHER', x=1920, y=0, focused=True,
                     activeWorkspace=dict(id=2, name='2'))
        saved = packet(self.clients)
        saved['monitors'] = [dict(MONITOR, focused=False), copy.deepcopy(other)]
        saved['cursor'] = [2400, 10]
        hc = FakeHyprctl(self.clients)
        hc.monitors = [copy.deepcopy(MONITOR), dict(other, focused=False)]
        restore = state.Restore(hc, saved)
        self.assertTrue(restore.split_focus())
        restore.restore_monitor_focus()
        self.assertEqual(hc.commands, [('movecursor', '2400 10')])
        with contextlib.redirect_stderr(io.StringIO()) as stderr:
            restore.verify()                              # the fake does not move monitor focus
        self.assertIn('note: focused monitor differs', stderr.getvalue())

    def test_final_verify_detects_group_order_damage(self):
        hc = FakeHyprctl(self.clients)
        hc.clients[0]['grouped'] = ['0xb', '0xa']
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError, 'state verification'):
                state.Restore(hc, packet(self.clients)).verify()

    def test_placement_recreates_an_empty_saved_monitor_workspace(self):
        hc = FakeHyprctl(self.clients)
        saved = packet(self.clients)
        saved['monitors'][0]['activeWorkspace'] = dict(id=7, name='7')
        restore = state.Restore(hc, saved)
        restore.placement()
        restore.active_workspaces()
        self.assertIn(('workspace', '7'), hc.commands)
        self.assertEqual(hc.monitors[0]['activeWorkspace'], dict(id=7, name='7'))

    def test_leave_recreates_empty_monitor_workspace_in_one_visit(self):
        hc = FakeHyprctl(self.clients)
        saved = packet(self.clients)
        empty = dict(MONITOR, id=1, name='EMPTY', focused=False,
                     activeWorkspace=dict(id=2, name='2'))
        saved['monitors'].append(copy.deepcopy(empty))
        hc.monitors.append(dict(empty, activeWorkspace=dict(id=9, name='9')))
        state.Restore(hc, saved).run()
        self.assertEqual([cmd for cmd in hc.commands if cmd[0] == 'focusmonitor'],
                         [('focusmonitor', 'EMPTY'), ('focusmonitor', 'TEST')])
        self.assertEqual([cmd for cmd in hc.commands if cmd[0] == 'workspace'],
                         [('workspace', '2'), ('workspace', '109'), ('workspace', '1')])
        self.assertEqual(hc.active, '0xa')
        self.assertTrue(hc.monitors[0]['focused'])
        self.assertEqual(hc.monitors[1]['activeWorkspace']['id'], 2)

    def test_unchanged_workspaces_need_no_explicit_monitor_visit(self):
        hc = FakeHyprctl(self.clients)
        state.Restore(hc, packet(self.clients)).run()
        self.assertFalse(any(name in ('focusmonitor', 'workspace') for name, _ in hc.commands))

    def test_existing_empty_workspace_on_wrong_monitor_is_moved_before_single_visit(self):
        hc = FakeHyprctl(self.clients)
        saved = packet(self.clients)
        saved['monitors'][0]['activeWorkspace'] = dict(id=7, name='7')
        saved['activewindow'] = {}
        other = dict(MONITOR, id=1, name='OTHER', focused=False,
                     activeWorkspace=dict(id=2, name='2'))
        saved['monitors'].append(copy.deepcopy(other))
        hc.monitors.append(dict(other, activeWorkspace=dict(id=7, name='7')))
        restore = state.Restore(hc, saved)
        restore.placement()
        restore.active_workspaces()
        self.assertIn(('moveworkspacetomonitor', '7 TEST'), hc.commands)
        self.assertLess(hc.commands.index(('moveworkspacetomonitor', '7 TEST')),
                        hc.commands.index(('workspace', '7')))
        self.assertEqual([cmd for cmd in hc.commands if cmd[0] == 'focusmonitor'],
                         [('focusmonitor', 'OTHER'), ('focusmonitor', 'TEST')])
        self.assertEqual([m['activeWorkspace']['id'] for m in hc.monitors], [7, 2])

    def test_final_focus_dispatch_errors_are_retried_and_dump_state(self):
        hc = FakeHyprctl(self.clients)
        base_batch = hc.batch

        def batch(commands):
            base_batch(commands)
            if any(name == 'focuswindow' for name, _ in commands):
                raise RuntimeError('focus transport failure')
        hc.batch = batch
        with contextlib.redirect_stderr(io.StringIO()) as stderr:
            with self.assertRaisesRegex(RuntimeError, 'focus transport failure'):
                state.Restore(hc, packet(self.clients)).focus(self.clients[0])
        self.assertEqual(sum(name == 'focuswindow' for name, _ in hc.commands), 2)
        self.assertIn('activewindow=', stderr.getvalue())
        self.assertIn('monitors=', stderr.getvalue())

    def test_failed_monitor_step_still_ends_on_saved_empty_focused_monitor(self):
        other = client('0xc', 0, 0, 600, 900, monitor=1, workspace=dict(id=2, name='2'))
        hc = FakeHyprctl(self.clients+[other])
        saved = packet(self.clients+[other])
        saved['monitors'][0]['activeWorkspace'] = dict(id=7, name='7')
        saved['activewindow'] = {}
        second = dict(MONITOR, id=1, name='OTHER', focused=False,
                      activeWorkspace=dict(id=2, name='2'))
        saved['monitors'].append(second)
        hc.monitors[0]['focused'] = False
        hc.monitors.append(dict(second, focused=True, activeWorkspace=dict(id=4, name='4')))
        hc.active = None
        hc.refuse_focus = True
        restore = state.Restore(hc, saved)
        with contextlib.redirect_stderr(io.StringIO()):
            restore.active_workspaces()
        self.assertTrue(restore.errors)
        self.assertTrue(hc.monitors[0]['focused'])
        self.assertEqual(hc.monitors[0]['activeWorkspace']['id'], 7)
        self.assertEqual(hc.commands[-3:], [('focusmonitor', 'TEST'),
                                          ('workspace', '107'), ('workspace', '7')])

    def test_workspaces_with_windows_are_visited_before_focus_dependent_restore(self):
        other = client('0xc', 0, 0, 600, 900, monitor=1, workspace=dict(id=2, name='2'))
        hc = FakeHyprctl(self.clients+[other])
        saved = packet(self.clients+[other])
        monitor = dict(MONITOR, id=1, name='OTHER', focused=False,
                       activeWorkspace=dict(id=2, name='2'))
        saved['monitors'].append(copy.deepcopy(monitor))
        hc.monitors.append(dict(monitor, activeWorkspace=dict(id=4, name='4')))
        hc.monitors[0]['activeWorkspace'] = dict(id=3, name='3')
        state.Restore(hc, saved).run()
        self.assertLess(hc.commands.index(('workspace', '1')),
                        hc.commands.index(('focuswindow', 'address:0xa')))
        self.assertEqual([m['activeWorkspace']['id'] for m in hc.monitors], [1, 2])
        self.assertEqual(hc.active, '0xa')

    def test_rebuild_aborts_before_preselect_if_focus_is_refused(self):
        hc = FakeHyprctl(self.clients)
        hc.clients[0]['size'][0] += 1
        hc.active = None
        hc.refuse_focus = True
        with contextlib.redirect_stderr(io.StringIO()) as stderr:
            with self.assertRaisesRegex(RuntimeError, 'focus did not reach'):
                state.Restore(hc, packet(self.clients)).run()
        self.assertFalse(any(name == 'layoutmsg' for name, _ in hc.commands))
        self.assertIn('workspace 1', stderr.getvalue())

    def test_later_failed_focus_does_not_preselect_or_insert_next_leaf(self):
        clients = [client('0xa', 12, 12, 600, 1029),
                   client('0xb', 656, 12, 1252, 400),
                   client('0xc', 656, 456, 1252, 585)]
        hc = FakeHyprctl(clients)
        hc.clients[0]['size'][0] += 1
        base_batch = hc.batch

        def batch(commands):
            base_batch(commands)
            if ('focuswindow', 'address:0xb') in commands:
                hc.active = None
        hc.batch = batch
        with contextlib.redirect_stderr(io.StringIO()) as stderr:
            with self.assertRaisesRegex(RuntimeError, 'focus did not reach 0xb'):
                state.Restore(hc, packet(clients)).rebuild_workspace('1', packet(clients)['trees']['1'])
        self.assertNotIn(('layoutmsg', 'preselect d'), hc.commands)
        self.assertNotIn(('settiled', 'address:0xc'), hc.commands)
        self.assertIn('workspace step aborted', stderr.getvalue())

    def test_rebuild_failure_does_not_skip_later_workspace(self):
        other = client('0xc', 0, 0, 600, 900, monitor=1, workspace=dict(id=2, name='2'))
        hc = FakeHyprctl(self.clients+[other])
        saved = packet(self.clients+[other])
        hc.clients[0]['size'][0] += 1
        hc.clients[2]['floating'] = True
        with contextlib.redirect_stderr(io.StringIO()):
            restore = state.Restore(hc, saved)
            restore.tiles()
        self.assertTrue(restore.errors)
        self.assertIn(('settiled', 'address:0xc'), hc.commands)
        self.assertFalse(hc.clients[2]['floating'])

    def test_fullscreen_failure_does_not_skip_other_fullscreen_windows(self):
        saved_clients = [dict(c, fullscreen=mode, fullscreenClient=mode)
                         for c, mode in zip(self.clients, (2, 1))]
        saved = packet(self.clients)
        saved['clients'] = saved_clients
        hc = FakeHyprctl(self.clients)
        base_batch = hc.batch

        def batch(commands):
            base_batch(commands)
            if ('focuswindow', 'address:0xa') in commands:
                hc.active = None
        hc.batch = batch
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError, 'focus did not reach'):
                state.Restore(hc, saved).run()
        self.assertEqual(hc.clients[1]['fullscreen'], 1)
        self.assertEqual(hc.clients[0]['fullscreen'], 0)

    def test_tile_failure_still_restores_fullscreen_and_keeps_snapshot(self):
        saved = packet(self.clients)
        saved['clients'][0].update(fullscreen=2, fullscreenClient=2,
                                   at=[3000, 420], size=[1920, 1080])
        hc = FakeHyprctl(self.clients)
        hc.clients[0]['size'][0] += 1
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stderr(io.StringIO()):
            path = pathlib.Path(directory)/'snapshot.json'
            path.write_text(json.dumps(saved))
            with self.assertRaisesRegex(RuntimeError, '0 px'):
                state.execute(hc, 'leave', path)
            self.assertTrue(path.exists())
        self.assertEqual(hc.clients[0]['fullscreen'], 2)
        self.assertEqual(hc.clients[0]['fullscreenClient'], 2)
        self.assertTrue(all(not c['floating'] for c in hc.clients))

    def test_scenario_f_rebuilds_under_both_fullscreen_modes_before_restoring_them(self):
        clients = [client('0xa', 3000, 420, 1920, 1080, fullscreen=2, fullscreenClient=2),
                   client('0xb', 3982, 459, 926, 1029),
                   client('0xc', 1932, 39, 1056, 1869, monitor=1,
                          workspace=dict(id=2, name='2'), fullscreen=1, fullscreenClient=1),
                   client('0xe', 1932, 996, 1056, 912, monitor=1, workspace=dict(id=2, name='2'))]
        second = dict(MONITOR, id=1, name='OTHER', x=1920, y=0, transform=1,
                      focused=False, activeWorkspace=dict(id=2, name='2'))
        saved = packet(self.clients)
        saved.update(clients=copy.deepcopy(clients), monitors=[copy.deepcopy(MONITOR), second],
                     trees=state.workspace_trees(clients, [MONITOR, second], METRICS))
        hc = FakeHyprctl(clients)
        hc.monitors = copy.deepcopy(saved['monitors'])
        for c in hc.clients:
            c.update(floating=True, fullscreen=0, fullscreenClient=0)
        hc.clients[0].update(at=[3012, 459], size=[900, 1029])
        hc.clients[2].update(size=[1056, 900])
        native_at_fullscreen = {}
        base_batch = hc.batch

        def batch(commands):
            for name, arg in commands:
                if name == 'fullscreenstate' and arg != '0 0':
                    active = next(c for c in hc.clients if c['address'] == hc.active)
                    native_at_fullscreen[hc.active] = [
                        (c['address'], c['at']+c['size'], c['floating']) for c in hc.clients
                        if c['workspace'] == active['workspace']]
                base_batch([(name, arg)])
                if name == 'resizewindowpixel':
                    geometry, address = arg.split(',address:')
                    next(c for c in hc.clients if c['address'] == address)['size'] = [
                        int(v) for v in geometry.split()[1:]]
                elif name == 'fullscreenstate' and arg != '0 0':
                    original = next(c for c in clients if c['address'] == hc.active)
                    active.update(at=list(original['at']), size=list(original['size']))
        hc.batch = batch
        with contextlib.redirect_stderr(io.StringIO()):
            state.Restore(hc, saved).run()
        self.assertEqual(native_at_fullscreen, {
            '0xa': [('0xa', [3012, 459, 926, 1029], False),
                    ('0xb', [3982, 459, 926, 1029], False)],
            '0xc': [('0xc', [1932, 39, 1056, 913], False),
                    ('0xe', [1932, 996, 1056, 912], False)]})
        self.assertEqual([(c['fullscreen'], c['fullscreenClient']) for c in hc.clients],
                         [(2, 2), (0, 0), (1, 1), (0, 0)])
        self.assertEqual(hc.active, '0xa')
        self.assertFalse(any(name in ('focusmonitor', 'workspace') for name, _ in hc.commands))

    def test_final_verify_detects_unexpected_focus_when_snapshot_has_none(self):
        hc = FakeHyprctl(self.clients)
        saved = packet(self.clients)
        saved['activewindow'] = {}
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError, 'state verification'):
                state.Restore(hc, saved).verify()

    def test_closed_peer_allows_survivor_geometry_to_change(self):
        hc = FakeHyprctl(self.clients[:1])
        hc.clients[0]['size'] = [1896, 1029]
        state.Restore(hc, packet(self.clients)).verify()

    def test_new_tile_allows_survivor_geometry_to_change(self):
        hc = FakeHyprctl(self.clients+[client('0xc', 0, 0, 300, 500)])
        hc.clients[0]['size'][0] -= 10
        state.Restore(hc, packet(self.clients)).verify()

    def test_transport_always_addresses_supplied_instance(self):
        result = type('Result', (), dict(returncode=0, stdout='[]', stderr=''))()
        with patch.object(state.subprocess, 'run', return_value=result) as run:
            self.assertEqual(state.Hyprctl('private-instance').query('clients'), [])
        self.assertEqual(run.call_args.args[0], ['hyprctl', '-i', 'private-instance', '-j', 'clients'])

    def test_offline_replay_uses_only_supplied_json(self):
        with tempfile.TemporaryDirectory() as directory:
            saved_path = pathlib.Path(directory)/'saved.json'
            current_path = pathlib.Path(directory)/'current.json'
            saved_path.write_text(json.dumps(packet(self.clients)))
            current_path.write_text(json.dumps(dict(clients=self.clients, monitors=[MONITOR],
                                                    cursorpos=dict(x=4173, y=812))))
            with patch.object(state.subprocess, 'run', side_effect=AssertionError('live transport invoked')):
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    self.assertEqual(state.main(['--replay-restore', str(saved_path), str(current_path)]), 0)
            self.assertIn('moveworkspacetomonitor', output.getvalue())
            self.assertTrue(output.getvalue().splitlines()[-2].endswith("'dispatch movecursor 4173 812'"))
            self.assertTrue(output.getvalue().splitlines()[-1].endswith("'dispatch focuswindow address:0xa'"))

    def test_nonzero_batch_response_is_rejected_even_if_process_succeeds(self):
        result = type('Result', (), dict(returncode=0, stdout='ok\nfailed to resize\nok', stderr=''))()
        with patch.object(state.subprocess, 'run', return_value=result):
            with self.assertRaisesRegex(RuntimeError, 'failed to resize'):
                state.Hyprctl('private-instance').batch([('settiled', 'address:0xa')])


REMEMBER = 'plugin:spatialoverview:canvas:remember_layout'
AUTO_PLACE = 'plugin:spatialoverview:canvas:auto_place'


class CanvasHyprctl(FakeHyprctl):
    def __init__(self, clients):
        super().__init__(clients)
        self.screens = 0
        self.options.update({REMEMBER: 1, AUTO_PLACE: 1})

    def keyword(self, name, value):
        self.events.append(('keyword', name, value))
        super().keyword(name, value)

    def batch(self, commands):
        super().batch(commands)
        for name, arg in commands:
            if name in ('resizewindowpixel', 'movewindowpixel'):
                geometry, address = arg.split(',address:')
                window = next(c for c in self.clients if c['address'] == address)
                window['size' if name == 'resizewindowpixel' else 'at'] = list(map(int, geometry.split()[1:]))


class CameraHyprctl(CanvasHyprctl):
    """Observable linked cameras with controllable viewport response."""
    def __init__(self, clients):
        super().__init__(clients)
        self.monitors.append(dict(MONITOR, id=1, name='OTHER', x=4920, focused=False))
        self.overview = dict(linked=True, leader='TEST', screens=[
            dict(monitor='TEST', zoom=.72, navigating=True, closing=False,
                 view=[2620, 210, 2680, 1500]),
            dict(monitor='OTHER', zoom=.72, navigating=True, closing=False,
                 view=[4540, 210, 2680, 1500])])
        self.response = 'success'
        self.nudged = False
        self.drift_after_placement = False
        self.pending_queries = 0
        self.readiness = []

    def query(self, name, *args, timeout=8):
        if name != 'spatialoverview':
            return super().query(name, *args, timeout=timeout)
        self.events.append(('query', name))
        if not self.screens:
            return dict(screens=[])
        if self.readiness:
            return copy.deepcopy(self.readiness.pop(0))
        if self.pending_queries:
            self.pending_queries -= 1
            if not self.pending_queries:
                self.overview['leader'] = 'TEST'
                self.overview['screens'][0]['view'] = [2620, 210, 2680, 1500]
        return copy.deepcopy(self.overview)

    def batch(self, commands):
        super().batch(commands)
        for name, arg in commands:
            if name == 'spatialoverview:canvas':
                if self.response == 'error':
                    raise RuntimeError('viewport failed')
                if arg == 'viewport 1 0':
                    self.nudged = True
                elif self.response != 'never' and (self.response != 'nudge' or self.nudged):
                    if self.response == 'delayed':
                        self.pending_queries = 3
                    else:
                        self.overview['leader'] = 'TEST'
                        self.overview['screens'][0]['view'] = [2620, 210, 2680, 1500]
            if name == 'movewindowpixel' and self.drift_after_placement:
                self.overview['leader'] = 'OTHER'


class CanvasCameraEntry(unittest.TestCase):
    def setUp(self):
        self.clients = [client('0xa', 3012, 459, 600, 1029)]
        self.hc = CameraHyprctl(self.clients)
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.path = pathlib.Path(directory)/'snapshot.json'
        self.stderr = self.enterContext(contextlib.redirect_stderr(io.StringIO()))
        self.sleep = self.enterContext(patch.object(state.time, 'sleep'))
        self.clock = 0
        def tick():
            self.clock += .02
            return self.clock
        self.enterContext(patch.object(state.time, 'monotonic', side_effect=tick))
        self.placement = [('setfloating', 'address:0xa'),
                          ('resizewindowpixel', 'exact 600 1029,address:0xa'),
                          ('movewindowpixel', 'exact 3012 459,address:0xa')]
        self.toggle = [('spatialoverview:overview', 'toggle all')]
        self.zero = [('spatialoverview:canvas', 'viewport 0 0')]
        self.nudge = [('spatialoverview:canvas', 'viewport 1 0')]

    def enter(self):
        state.execute(self.hc, 'enter', self.path)
        self.assertIn(self.placement, self.hc.batches)
        self.assertEqual(self.hc.clients[0]['at']+self.hc.clients[0]['size'],
                         [3012, 459, 600, 1029])
        self.assertEqual(self.hc.options[AUTO_PLACE], 1)

    def test_focused_leader_centred_has_no_camera_batch_or_post_placement_query(self):
        self.enter()
        self.assertEqual(self.hc.batches, [self.toggle, self.placement])
        placed = self.hc.events.index(self.placement[-1])
        self.assertNotIn(('query', 'spatialoverview'), self.hc.events[placed+1:])
        self.sleep.assert_not_called()

    def test_other_leader_is_corrected_between_toggle_and_placement(self):
        self.hc.overview['leader'] = 'OTHER'
        self.enter()
        self.assertEqual(self.hc.batches, [self.toggle, self.zero, self.placement])
        self.assertEqual(self.hc.overview['leader'], 'TEST')
        placed = self.hc.events.index(self.placement[-1])
        self.assertEqual(self.hc.events[placed+1:].count(('query', 'spatialoverview')), 1)

    def test_focused_leader_off_centre_is_corrected(self):
        self.hc.overview['screens'][0]['view'][0] -= 584
        self.enter()
        self.assertEqual(self.hc.batches, [self.toggle, self.zero, self.placement])
        self.assertEqual(self.hc.overview['screens'][0]['view'], [2620, 210, 2680, 1500])

    def test_centred_follower_needs_one_nudge_a_frame_before_zero(self):
        self.hc.overview['leader'] = 'OTHER'
        self.hc.response = 'nudge'
        self.enter()
        self.assertEqual(self.hc.batches,
                         [self.toggle, self.zero, self.nudge, self.zero, self.placement])
        self.sleep.assert_any_call(.05)
        self.assertNotIn('warning:', self.stderr.getvalue())

    def test_failed_correction_warns_and_places_windows_with_bounded_dispatches(self):
        self.hc.overview['leader'] = 'OTHER'
        self.hc.response = 'never'
        self.enter()
        self.assertIn('warning:', self.stderr.getvalue())
        self.assertEqual(self.hc.batches, [self.toggle, self.zero, self.nudge, self.zero,
                                         self.placement, self.zero, self.nudge, self.zero])

    def test_state_without_camera_keys_is_an_immediate_noop(self):
        self.hc.overview = dict(screens=[{}, {}])
        self.enter()
        self.assertEqual(self.hc.batches, [self.toggle, self.placement])
        self.sleep.assert_not_called()

    def test_rotated_scaled_monitor_uses_swapped_logical_extents(self):
        self.hc.monitors[0].update(transform=1, scale=2)
        # Logical size is 540 x 960; centre is (3270, 900).
        self.hc.overview['screens'][0]['view'] = [2520, -100, 1500, 2000]
        self.enter()
        self.assertEqual(self.hc.batches, [self.toggle, self.placement])

    def test_placement_camera_drift_gets_one_more_correction(self):
        self.hc.overview['leader'] = 'OTHER'
        self.hc.drift_after_placement = True
        self.enter()
        self.assertEqual(self.hc.batches, [self.toggle, self.zero, self.placement, self.zero])
        self.assertEqual(self.hc.overview['leader'], 'TEST')

    def test_dry_enter_skips_camera_queries_and_sleeps(self):
        self.hc.dry = True
        self.hc.overview['leader'] = 'OTHER'
        self.enter()
        self.assertEqual(self.hc.batches, [self.toggle, self.placement])
        self.assertEqual(self.hc.events.count(('query', 'spatialoverview')), 1)
        self.sleep.assert_not_called()

    def test_camera_waits_for_all_screens_and_leader_before_dispatch(self):
        initial = copy.deepcopy(self.hc.overview)
        initial['leader'] = ''
        initial['screens'][1]['navigating'] = False
        self.hc.readiness = [initial, initial, initial]
        self.hc.overview['leader'] = 'OTHER'
        self.enter()
        self.assertEqual(self.hc.batches, [self.toggle, self.zero, self.placement])
        self.sleep.assert_any_call(.02)

    def test_incomplete_camera_state_times_out_without_dispatch(self):
        self.hc.overview['screens'][1].pop('view')
        self.enter()
        self.assertEqual(self.hc.batches, [self.toggle, self.placement])
        self.assertLess(self.clock, 1.7)

    def test_delayed_correction_is_observed_before_placement(self):
        self.hc.overview['leader'] = 'OTHER'
        self.hc.response = 'delayed'
        self.enter()
        self.assertEqual(self.hc.batches, [self.toggle, self.zero, self.placement])
        self.assertEqual(self.hc.overview['leader'], 'TEST')
        self.sleep.assert_any_call(.02)

    def test_viewport_error_warns_and_keeps_placement(self):
        self.hc.overview['leader'] = 'OTHER'
        self.hc.response = 'error'
        self.enter()
        self.assertIn('warning:', self.stderr.getvalue())
        self.assertEqual(self.hc.batches, [self.toggle, self.zero, self.placement, self.zero])

    def test_focused_monitor_without_canvas_is_skipped(self):
        self.hc.monitors[0]['name'] = 'ABSENT'
        self.enter()
        self.assertEqual(self.hc.batches, [self.toggle, self.placement])

    def test_small_centre_error_is_within_tolerance(self):
        self.hc.overview['screens'][0]['view'][0] += 1.5
        self.enter()
        self.assertEqual(self.hc.batches, [self.toggle, self.placement])


class CanvasEntry(unittest.TestCase):
    def setUp(self):
        self.clients = [client('0xa', 3012, 459, 600, 1029),
                        client('0xb', 3700, 500, 400, 300, floating=True)]
        self.enterContext(contextlib.redirect_stderr(io.StringIO()))
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = pathlib.Path(self.directory.name)/'snapshot.json'
        self.journal = pathlib.Path(str(self.path)+'.options')

    def test_enter_options_and_one_post_open_batch_then_leave_restores_journal(self):
        hc = CanvasHyprctl(self.clients)
        state.execute(hc, 'enter', self.path)
        self.assertEqual(json.loads(self.journal.read_text()), {REMEMBER: 1, AUTO_PLACE: 1})
        self.assertEqual(hc.options[REMEMBER], 0)
        self.assertEqual(hc.options[AUTO_PLACE], 1)
        self.assertEqual(hc.batches, [[('spatialoverview:overview', 'toggle all')], [
            ('setfloating', 'address:0xa'), ('resizewindowpixel', 'exact 600 1029,address:0xa'),
            ('movewindowpixel', 'exact 3012 459,address:0xa'),
            ('resizewindowpixel', 'exact 400 300,address:0xb'),
            ('movewindowpixel', 'exact 3700 500,address:0xb')]])
        opened = hc.events.index(('spatialoverview:overview', 'toggle all'))
        self.assertLess(hc.events.index(('keyword', REMEMBER, 0)), opened)
        self.assertLess(hc.events.index(('keyword', AUTO_PLACE, 0)), opened)
        self.assertGreater(hc.events.index(('keyword', AUTO_PLACE, 1)),
                           hc.events.index(('movewindowpixel', 'exact 3700 500,address:0xb')))
        self.assertEqual(hc.events[opened+1:].count(('query', 'clients')), 1)
        self.assertNotIn(('keyword', REMEMBER, 1), hc.events)
        state.execute(hc, 'leave', self.path)
        self.assertEqual(hc.options[REMEMBER], 1)
        self.assertFalse(self.journal.exists())
        self.assertFalse(self.path.exists())

    def test_open_requeries_floating_state_and_skips_disappeared_windows(self):
        hc = CanvasHyprctl(self.clients)
        batch = hc.batch
        def plugin(commands):
            batch(commands)
            if commands == [('spatialoverview:overview', 'toggle all')]:
                hc.clients.pop()
                hc.clients[0]['floating'] = True
                hc.clients[0]['at'] = [0, 0]
                hc.clients[0]['size'] = [10, 10]
        with patch.object(hc, 'batch', side_effect=plugin):
            state.execute(hc, 'enter', self.path)
        self.assertEqual(hc.batches[-1], [('resizewindowpixel', 'exact 600 1029,address:0xa'),
                                        ('movewindowpixel', 'exact 3012 459,address:0xa')])
        self.assertEqual(hc.clients[0]['at']+hc.clients[0]['size'], [3012, 459, 600, 1029])

    def test_existing_crash_journal_keeps_originals(self):
        hc = CanvasHyprctl(self.clients)
        hc.options.update({REMEMBER: 0, AUTO_PLACE: 0})
        self.journal.write_text(json.dumps({REMEMBER: 1, AUTO_PLACE: 7}))
        state.execute(hc, 'enter', self.path)
        self.assertEqual(json.loads(self.journal.read_text()), {REMEMBER: 1, AUTO_PLACE: 7})
        self.assertEqual(hc.options[AUTO_PLACE], 7)
        state.execute(hc, 'leave', self.path)
        self.assertEqual(hc.options[REMEMBER], 1)
        self.assertEqual(hc.options[AUTO_PLACE], 7)

    def test_pre_toggle_error_restores_both_and_keeps_snapshot(self):
        hc = CanvasHyprctl(self.clients)
        keyword = hc.keyword
        def fail(name, value):
            if name == AUTO_PLACE and value == 0:
                raise RuntimeError('option write failed')
            keyword(name, value)
        with patch.object(hc, 'keyword', side_effect=fail):
            with self.assertRaisesRegex(RuntimeError, 'option write failed'):
                state.execute(hc, 'enter', self.path)
        self.assertEqual(hc.options[REMEMBER], 1)
        self.assertEqual(hc.options[AUTO_PLACE], 1)
        self.assertTrue(self.path.exists())
        self.assertEqual(hc.batches, [])

    def test_post_toggle_error_restores_auto_place_and_keeps_journal_until_leave(self):
        hc = CanvasHyprctl(self.clients)
        batch = hc.batch
        def fail(commands):
            if any(name == 'resizewindowpixel' for name, _ in commands):
                raise RuntimeError('placement failed')
            batch(commands)
        with patch.object(hc, 'batch', side_effect=fail):
            with self.assertRaisesRegex(RuntimeError, 'placement failed'):
                state.execute(hc, 'enter', self.path)
        self.assertEqual(hc.options[REMEMBER], 0)
        self.assertEqual(hc.options[AUTO_PLACE], 1)
        self.assertTrue(self.path.exists())
        self.assertTrue(self.journal.exists())
        state.execute(hc, 'leave', self.path)
        self.assertEqual(hc.options[REMEMBER], 1)
        self.assertFalse(self.journal.exists())

    def test_poll_waits_for_open_and_timeout_retains_evidence(self):
        for opens in (True, False):
            with self.subTest(opens=opens):
                hc = CanvasHyprctl(self.clients)
                query = hc.query
                calls = 0
                def delayed(name, *args):
                    nonlocal calls
                    if name == 'spatialoverview':
                        calls += 1
                        return dict(screens=[{}] if opens and calls >= 4 else [])
                    return query(name, *args)
                with patch.object(hc, 'query', side_effect=delayed), patch.object(state.time, 'sleep') as sleep:
                    if opens:
                        state.execute(hc, 'enter', self.path)
                        self.assertEqual(sleep.call_count, 2)
                    else:
                        with self.assertRaisesRegex(RuntimeError, 'canvas did not open'):
                            state.execute(hc, 'enter', self.path)
                        self.assertEqual(hc.batches, [[('spatialoverview:overview', 'toggle all')]])
                        self.assertTrue(self.path.exists())
                        self.assertTrue(self.journal.exists())
                self.assertEqual(hc.options[AUTO_PLACE], 1)
                self.assertEqual(hc.options[REMEMBER], 0)

    def test_every_leave_exit_restores_and_removes_option_journal(self):
        for scenario in ('missing', 'unusable', 'close_error', 'restore_error', 'query_error', 'reopened'):
            with self.subTest(scenario=scenario), contextlib.redirect_stderr(io.StringIO()):
                hc = CanvasHyprctl(self.clients)
                hc.screens = 1
                hc.options.update({REMEMBER: 0, AUTO_PLACE: 0})
                self.path.unlink(missing_ok=True)
                if scenario != 'missing':
                    self.path.write_text('invalid' if scenario == 'unusable' else json.dumps(packet(self.clients)))
                self.journal.write_text(json.dumps({REMEMBER: 1, AUTO_PLACE: 7}))
                with contextlib.ExitStack() as stack:
                    if scenario == 'close_error':
                        stack.enter_context(patch.object(hc, 'batch', side_effect=RuntimeError('close failed')))
                    elif scenario == 'restore_error':
                        stack.enter_context(patch.object(state.Restore, 'run', side_effect=RuntimeError('restore failed')))
                    elif scenario == 'query_error':
                        stack.enter_context(patch.object(hc, 'query', side_effect=RuntimeError('query failed')))
                    elif scenario == 'reopened':
                        def reopen(restore, before_focus):
                            hc.screens = 1
                            before_focus()
                        stack.enter_context(patch.object(state.Restore, 'run', reopen))
                    if scenario in ('missing', 'unusable'):
                        state.execute(hc, 'leave', self.path)
                    else:
                        with self.assertRaises(RuntimeError):
                            state.execute(hc, 'leave', self.path)
                self.assertEqual(hc.options[REMEMBER], 1)
                self.assertEqual(hc.options[AUTO_PLACE], 7)
                self.assertFalse(self.journal.exists())

    def test_set_aside_restores_old_journal_before_new_snapshot_and_enter(self):
        hc = CanvasHyprctl(self.clients)
        hc.options.update({REMEMBER: 0, AUTO_PLACE: 0})
        self.path.write_text('stale evidence')
        self.journal.write_text(json.dumps({REMEMBER: 7, AUTO_PLACE: 8}))
        with contextlib.redirect_stderr(io.StringIO()):
            state.execute(hc, 'enter', self.path)
        self.assertEqual(json.loads(self.journal.read_text()), {REMEMBER: 7, AUTO_PLACE: 8})
        self.assertEqual(hc.options[AUTO_PLACE], 8)
        self.assertLess(hc.events.index(('keyword', REMEMBER, 7)), hc.events.index(('query', 'clients')))

    def test_restore_option_failures_try_both_raise_and_remove_journal(self):
        hc = CanvasHyprctl(self.clients)
        self.path.write_text(json.dumps(packet(self.clients)))
        self.journal.write_text(json.dumps({REMEMBER: 1, AUTO_PLACE: 1}))
        keyword = hc.keyword
        def fail(name, value):
            if name == AUTO_PLACE:
                raise RuntimeError('auto restore failed')
            keyword(name, value)
        with patch.object(hc, 'keyword', side_effect=fail), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError, 'could not restore.*auto restore failed'):
                state.execute(hc, 'leave', self.path)
        self.assertIn(('keyword', REMEMBER, 1), hc.events)
        self.assertFalse(self.journal.exists())
        self.assertTrue(self.path.exists())

    def test_journal_exists_before_first_option_mutation(self):
        hc = CanvasHyprctl(self.clients)
        keyword = hc.keyword
        def checked(name, value):
            self.assertEqual(json.loads(self.journal.read_text()), {REMEMBER: 1, AUTO_PLACE: 1})
            keyword(name, value)
        with patch.object(hc, 'keyword', side_effect=checked):
            state.execute(hc, 'enter', self.path)

    def test_entry_skips_unmapped_and_reused_addresses(self):
        hc = CanvasHyprctl(self.clients)
        batch = hc.batch
        def plugin(commands):
            batch(commands)
            if commands == [('spatialoverview:overview', 'toggle all')]:
                hc.clients[0]['mapped'] = False
                hc.clients[1]['stableId'] = 'replacement'
        with patch.object(hc, 'batch', side_effect=plugin):
            state.execute(hc, 'enter', self.path)
        self.assertEqual(hc.commands, [('spatialoverview:overview', 'toggle all')])

    def test_dry_leave_preserves_journal_and_snapshot(self):
        hc = CanvasHyprctl(self.clients)
        hc.dry = True
        self.path.write_text(json.dumps(packet(self.clients)))
        self.journal.write_text(json.dumps({REMEMBER: 1, AUTO_PLACE: 1}))
        state.execute(hc, 'leave', self.path)
        self.assertTrue(self.path.exists())
        self.assertTrue(self.journal.exists())
        self.assertEqual(hc.options[REMEMBER], 1)

    def test_toggle_dispatch_error_keeps_remember_disabled_in_case_plugin_opened(self):
        hc = CanvasHyprctl(self.clients)
        with patch.object(hc, 'batch', side_effect=RuntimeError('toggle failed')):
            with self.assertRaisesRegex(RuntimeError, 'toggle failed'):
                state.execute(hc, 'enter', self.path)
        self.assertEqual(hc.options[REMEMBER], 0)
        self.assertEqual(hc.options[AUTO_PLACE], 1)
        self.assertTrue(self.path.exists())
        self.assertTrue(self.journal.exists())

    def test_special_windows_still_tiled_after_open_are_skipped(self):
        windows = [client('0xa', 3012, 459, 600, 1029,
                          workspace=dict(id=-99, name='special:tiled')),
                   client('0xb', 3700, 500, 400, 300, floating=True,
                          workspace=dict(id=-98, name='special:floating'))]
        hc = CanvasHyprctl(windows)
        state.execute(hc, 'enter', self.path)
        self.assertEqual(hc.batches[-1], [('resizewindowpixel', 'exact 400 300,address:0xb'),
                                        ('movewindowpixel', 'exact 5812 500,address:0xb')])
        self.assertEqual(json.loads(self.path.read_text())['clients'], windows)

    def test_journal_write_failure_does_not_change_options_or_toggle(self):
        hc = CanvasHyprctl(self.clients)
        save = state.save_atomic
        def fail(path, data):
            if path == self.journal:
                raise OSError('journal write failed')
            save(path, data)
        with patch.object(state, 'save_atomic', side_effect=fail):
            with self.assertRaisesRegex(OSError, 'journal write failed'):
                state.execute(hc, 'enter', self.path)
        self.assertTrue(self.path.exists())
        self.assertEqual(hc.batches, [])
        self.assertEqual(hc.options[REMEMBER], 1)
        self.assertEqual(hc.options[AUTO_PLACE], 1)

    def test_early_enter_errors_restore_originals_from_crash_journal(self):
        for failed_query in ('spatialoverview', 'clients'):
            with self.subTest(failed_query=failed_query):
                hc = CanvasHyprctl(self.clients)
                hc.options.update({REMEMBER: 0, AUTO_PLACE: 0})
                self.journal.write_text(json.dumps({REMEMBER: 1, AUTO_PLACE: 7}))
                query = hc.query
                def fail(name, *args):
                    if name == failed_query:
                        raise RuntimeError('early query failed')
                    return query(name, *args)
                with patch.object(hc, 'query', side_effect=fail):
                    with self.assertRaisesRegex(RuntimeError, 'early query failed'):
                        state.execute(hc, 'enter', self.path)
                self.assertEqual(hc.options[REMEMBER], 1)
                self.assertEqual(hc.options[AUTO_PLACE], 7)
                self.assertEqual(hc.batches, [])

    def test_post_open_option_restore_failure_keeps_snapshot_and_journal(self):
        hc = CanvasHyprctl(self.clients)
        keyword = hc.keyword
        def fail(name, value):
            if name == AUTO_PLACE and value == 1:
                raise RuntimeError('auto restore failed')
            keyword(name, value)
        with patch.object(hc, 'keyword', side_effect=fail):
            with self.assertRaisesRegex(RuntimeError, 'could not restore.*auto restore failed'):
                state.execute(hc, 'enter', self.path)
        self.assertEqual(hc.options[REMEMBER], 0)
        self.assertTrue(self.path.exists())
        self.assertTrue(self.journal.exists())

    def test_dry_enter_does_not_write_journal_snapshot_or_poll(self):
        hc = CanvasHyprctl(self.clients)
        hc.dry = True
        with patch.object(state.time, 'sleep', side_effect=AssertionError('dry poll')), \
             contextlib.redirect_stderr(io.StringIO()):
            state.execute(hc, 'enter', self.path)
        self.assertFalse(self.path.exists())
        self.assertFalse(self.journal.exists())
        self.assertEqual(sum(event == ('query', 'spatialoverview') for event in hc.events), 1)
        self.assertEqual(hc.batches[-1][-1], ('movewindowpixel', 'exact 3700 500,address:0xb'))

    def test_restore_floating_geometry_comes_from_snapshot_not_canvas(self):
        hc = CanvasHyprctl([self.clients[1]])
        saved = packet([self.clients[1]])
        hc.clients[0]['at'] = [9000, -500]
        hc.clients[0]['size'] = [30, 20]
        state.Restore(hc, saved).run()
        self.assertEqual(hc.clients[0]['at']+hc.clients[0]['size'], [3700, 500, 400, 300])
        self.assertEqual(saved['clients'][0]['at']+saved['clients'][0]['size'], [3700, 500, 400, 300])


ANIMATIONS = 'animations:enabled'


class ZoomHyprctl(CanvasHyprctl):
    def __init__(self, clients, screens=None):
        super().__init__(clients)
        self.screens = 1
        self.view = screens if screens is not None else [dict(navigating=True, zoom=.72)]
        self.zoom_frames = [[dict(navigating=False, zoom=1)]]
        self.zooming = False
        self.options[ANIMATIONS] = 1
        # Geometry is supplied by the fixture, not a full dwindle simulation.
        # Re-insertion can recover it; settiled on an existing tile cannot.
        self.native_geometry = {c['address']: (c['at'][:], c['size'][:]) for c in clients}
        self.detached_tiles = set()

    def close_canvas(self):
        shared = copy.deepcopy(self.monitors[0]['activeWorkspace'])
        for monitor in self.monitors:
            monitor['activeWorkspace'] = copy.deepcopy(shared)
        for c in self.clients:
            if c['floating']:
                c['floating'] = False
                monitor = next(m for m in self.monitors if m['id'] == c['monitor'])
                c['at'] = [monitor['x']+12, monitor['y']+39]
                c['size'] = [monitor['width']-24, monitor['height']-51]

    def query(self, name, *args, timeout=8):
        result = super().query(name, *args)
        if name == 'spatialoverview':
            if not self.screens:
                return dict(screens=[])
            if self.zooming and self.zoom_frames:
                self.view = self.zoom_frames.pop(0)
            self.events.append(('view', copy.deepcopy(self.view)))
            return dict(screens=copy.deepcopy(self.view))
        return result

    def batch(self, commands):
        # Execute close synchronously, before later items in the SAME batch.
        # CanvasHyprctl's geometry pass runs after a batch, so run each item here.
        self.batches.append(list(commands))
        for name, arg in commands:
            window = next((c for c in self.clients if c['address'] == arg.removeprefix('address:')), None)
            was_floating = window and window['floating']
            try:
                super().batch([(name, arg)])
            finally:
                self.batches.pop()
            if name == 'setfloating' and window:
                self.detached_tiles.update(window['grouped'] or [window['address']])
            elif name == 'settiled' and window and was_floating:
                for c in self.clients:
                    if c['address'] in (window['grouped'] or [window['address']]):
                        c['floating'] = False
                        if c['address'] in self.detached_tiles:
                            at, size = self.native_geometry[c['address']]
                            c['at'], c['size'] = at[:], size[:]
                            self.detached_tiles.remove(c['address'])
        if ('spatialoverview:overview', 'toggle all') in commands:
            self.zooming = True


class CountingZoomHyprctl(ZoomHyprctl):
    def __init__(self, *args):
        super().__init__(*args)
        self.mutations = []
        self.in_batch = False

    def keyword(self, name, value):
        if not self.in_batch:
            self.mutations.append(('keyword', name, value))
        super().keyword(name, value)

    def batch(self, commands):
        self.mutations.append(('batch', list(commands)))
        self.in_batch = True
        try:
            super().batch(commands)
        finally:
            self.in_batch = False


class CanvasLeave(unittest.TestCase):
    def setUp(self):
        self.clients = [client('0xa', 3012, 459, 600, 1029),
                        client('0xb', 3700, 500, 400, 300, floating=True)]
        self.enterContext(contextlib.redirect_stderr(io.StringIO()))
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.path = pathlib.Path(directory)/'snapshot.json'
        self.journal = pathlib.Path(str(self.path)+'.options')
        self.marker = pathlib.Path(str(self.path)+'.restoring')
        self.path.write_text(json.dumps(packet(self.clients)))

    def assert_atomic_rebuild(self, hc, saved):
        batches = [commands for commands in getattr(hc, 'calls', hc.batches)
                   if ('spatialoverview:overview', 'toggle all') not in commands]
        self.assertEqual(len(batches), 1)
        commands = batches[0]
        first = next(i for i in range(1, len(commands)) if commands[i][0] != 'keyword')
        monitors = sorted(saved['monitors'], key=lambda m: bool(m.get('focused')))
        repair = []
        for m in monitors:
            repair.append(('focusmonitor', m['name']))
            if m.get('focused'):
                repair.append(commands[first+len(repair)])
                self.assertEqual(repair[-1][0], 'workspace')
                self.assertGreater(int(repair[-1][1]), 100)
            repair.append(('workspace', state.workspace_arg(m['activeWorkspace'])))
        self.assertEqual(commands[first:first+len(repair)], repair)
        for tree in saved['trees'].values():
            representatives = [tile['representative'] for tile in state.leaves(tree)]
            tiled = min(commands.index(('settiled', 'address:'+a)) for a in representatives)
            for address in representatives:
                self.assertLess(commands.index(('setfloating', 'address:'+address)), tiled)
        self.assertEqual(commands[-1], ('movecursor', '4173 812'))
        self.assertEqual(commands[-2], ('focuswindow', 'address:'+saved['activewindow']['address']))
        off = hc.events.index(('spatialoverview:overview', 'off all'))
        pointer = max(i for i, event in enumerate(hc.events) if event == commands[-1])
        self.assertFalse(any(event[0] == 'query' for event in hc.events[off:pointer]))
        self.assertTrue(all(event[0] == 'query' for event in hc.events[pointer+1:-1]))
        state.Restore(hc, saved).verify()

    def test_atomic_leave_collects_repairs_and_pointer_in_one_mutating_call(self):
        for moved in (False, True):
            with self.subTest(moved=moved):
                hc = CountingZoomHyprctl(self.clients, [dict(navigating=False, zoom=1)])
                hc.clients[0]['floating'] = True
                if moved:
                    hc.clients[1]['at'] = [4100, 900]
                saved = packet(self.clients)
                empty = dict(MONITOR, id=1, name='EMPTY', focused=False,
                             activeWorkspace=dict(id=2, name='2'))
                saved['monitors'].append(copy.deepcopy(empty))
                hc.monitors.append(dict(empty, activeWorkspace=dict(id=9, name='9')))
                hc.poison_repair = ('EMPTY', 2)
                self.path.write_text(json.dumps(saved))
                state.execute(hc, 'leave', self.path)
                disable = hc.events.index(('keyword', ANIMATIONS, 0))
                enable = hc.events.index(('keyword', ANIMATIONS, 1))
                batches = [commands for commands in hc.batches
                           if ('spatialoverview:overview', 'toggle all') not in commands]
                self.assertEqual(len(batches), 1)
                start = hc.mutations.index(('keyword', ANIMATIONS, 0))
                end = hc.mutations.index(('keyword', ANIMATIONS, 1))
                self.assertEqual(hc.mutations[start+1:end], [('batch', batches[0])])
                self.assertEqual(batches[0][0], ('spatialoverview:overview', 'off all'))
                self.assertEqual(batches[0][-1], ('movecursor', '4173 812'))
                self.assertTrue(any(name == 'workspace' and int(arg) > 100
                                    for name, arg in batches[0] if arg.isdigit()))
                direct_mutations = [event for event in hc.events[disable+1:enable]
                                    if len(event) == 3 and event[0] == 'keyword']
                self.assertTrue(all(('keyword', event[1]+' '+str(event[2])) in batches[0]
                                    for event in direct_mutations))
                off = hc.events.index(('spatialoverview:overview', 'off all'))
                for name in ('clients', 'monitors', 'workspaces'):
                    self.assertEqual(hc.events[disable+1:off].count(('query', name)), 1)
                self.assertEqual([m['activeWorkspace']['id'] for m in hc.monitors], [1, 2])
                self.assertEqual(hc.clients, self.clients)
                self.assertEqual(hc.options[ANIMATIONS], 1)
                self.assertFalse(self.marker.exists())
                self.assertFalse(self.journal.exists())
                self.assert_atomic_rebuild(hc, saved)

    def test_atomic_difference_or_batch_error_falls_back_and_restores_animations(self):
        for failure in ('difference', 'pointer', 'error', 'reopened'):
            with self.subTest(failure=failure):
                hc = ZoomHyprctl(self.clients)
                hc.clients[0]['floating'] = True
                self.path.write_text(json.dumps(packet(self.clients)))
                batch = hc.batch
                injected = False
                def damage(commands):
                    nonlocal injected
                    batch(commands)
                    if (not injected and ('spatialoverview:overview', 'off all') in commands
                            and ('settiled', 'address:0xa') in commands):
                        injected = True
                        if failure != 'pointer':
                            hc.clients[0]['floating'] = True
                        hc.cursor = dict(x=12, y=34)
                        if failure == 'error':
                            raise RuntimeError('atomic batch refused after partial application')
                        if failure == 'reopened':
                            hc.screens = 1
                with patch.object(hc, 'batch', side_effect=damage):
                    state.execute(hc, 'leave', self.path)
                self.assertTrue(injected)
                self.assertGreater(len(hc.batches), 1)
                self.assertEqual(hc.clients, self.clients)
                self.assertEqual(hc.cursor, dict(x=4173, y=812))
                self.assertEqual(hc.screens, 0)
                self.assertEqual(hc.events[-1], ('keyword', ANIMATIONS, 1))
                self.assertFalse(self.path.exists())
                self.assertFalse(self.marker.exists())
                self.assertFalse(self.journal.exists())

    def test_atomic_error_repairs_windows_even_if_close_retry_reports_an_error(self):
        hc = ZoomHyprctl(self.clients)
        hc.clients[0]['floating'] = True
        batch = hc.batch
        def fail_close(commands):
            if ('spatialoverview:overview', 'off all') in commands:
                batch(commands[:2])
                raise RuntimeError('close retry reports error')
            batch(commands)
        with patch.object(hc, 'batch', side_effect=fail_close):
            with self.assertRaisesRegex(RuntimeError, 'close retry reports error'):
                state.execute(hc, 'leave', self.path)
        self.assertEqual(hc.clients, self.clients)
        self.assertEqual(hc.cursor, dict(x=4173, y=812))
        self.assertEqual(hc.options[ANIMATIONS], 1)
        self.assertTrue(self.path.exists())
        self.assertFalse(self.marker.exists())
        self.assertFalse(self.journal.exists())

    def test_four_tiles_on_two_monitors_restore_without_a_visible_scratch_switch(self):
        windows = [client('0xa', 3012, 459, 1200, 400), client('0xb', 3556, 903, 1352, 585),
                   client('0xc', 4256, 459, 652, 400), client('0xd', 3012, 903, 500, 585)]
        for moved in (False, True):
            with self.subTest(moved=moved):
                hc = ZoomHyprctl(windows)
                saved = packet(windows)
                other = dict(MONITOR, id=1, name='OTHER', focused=False,
                             activeWorkspace=dict(id=2, name='2'))
                saved['monitors'].append(copy.deepcopy(other))
                hc.monitors.append(copy.deepcopy(other))
                saved['activewindow'] = dict(address='0xc')
                hc.active = '0xc'
                for c in hc.clients:
                    c['floating'] = True
                    if moved:
                        c['at'] = [c['at'][0]+100, c['at'][1]+50]
                self.path.write_text(json.dumps(saved))
                batch = hc.batch
                rendered = []
                def render(commands):
                    batch(commands)
                    rendered.append(([m['activeWorkspace']['id'] for m in hc.monitors],
                                     copy.deepcopy(hc.clients)))
                with patch.object(hc, 'batch', side_effect=render):
                    state.execute(hc, 'leave', self.path)
                close = [commands for commands in hc.batches
                         if ('spatialoverview:overview', 'off all') in commands]
                self.assertEqual(len(close), 1)
                for address in ('0xa', '0xb', '0xc', '0xd'):
                    self.assertIn(('settiled', 'address:'+address), close[0])
                self.assertTrue(any(name == 'layoutmsg' for name, _ in close[0]))
                self.assertEqual(close[0][-1], ('movecursor', '4173 812'))
                self.assertEqual(rendered[-1], ([1, 2], windows))
                self.assertEqual(len(rendered), 2)  # zoom toggle, then the atomic close/restore
                self.assertEqual(hc.options[ANIMATIONS], 1)
                self.assert_atomic_rebuild(hc, saved)
                first_tile = close[0].index(('settiled', 'address:0xa'))
                last_resize = close[0].index(('resizewindowpixel', 'exact 500 585,address:0xd'))
                native = [(name, arg) for name, arg in close[0][first_tile-1:last_resize+1]
                          if name != 'movecursor']
                self.assertEqual(native, [
                    ('focuswindow', 'address:0xa'), ('settiled', 'address:0xa'),
                    ('focuswindow', 'address:0xa'), ('layoutmsg', 'preselect d'),
                    ('settiled', 'address:0xd'), ('resizewindowpixel', 'exact 1896 400,address:0xa'),
                    ('focuswindow', 'address:0xa'), ('layoutmsg', 'preselect r'),
                    ('settiled', 'address:0xc'), ('resizewindowpixel', 'exact 1200 400,address:0xa'),
                    ('focuswindow', 'address:0xd'), ('layoutmsg', 'preselect r'),
                    ('settiled', 'address:0xb'), ('resizewindowpixel', 'exact 500 585,address:0xd')])

    def test_atomic_close_repairs_hidden_workspace_and_shifted_window_placement(self):
        windows = self.clients + [
            client('0xe', 3012, 459, 1200, 1029, monitor=1, workspace=dict(id=7, name='7')),
            client('0xf', 4256, 459, 652, 1029, monitor=1, workspace=dict(id=7, name='7'))]
        other = dict(MONITOR, id=1, name='OTHER', focused=False,
                     activeWorkspace=dict(id=2, name='2'))
        saved = packet(windows)
        saved['monitors'].append(other)
        saved['trees'] = state.workspace_trees(windows, saved['monitors'], METRICS)
        hc = CountingZoomHyprctl(windows, [dict(navigating=False, zoom=1)])
        hc.monitors = copy.deepcopy(saved['monitors'])
        for c in hc.clients:
            c['floating'] = True
        close = hc.close_canvas
        def shift():
            close()
            for c in hc.clients:
                c['workspace'], c['monitor'] = dict(id=1, name='1'), 0
        self.path.write_text(json.dumps(saved))
        with patch.object(hc, 'close_canvas', side_effect=shift):
            state.execute(hc, 'leave', self.path)
        self.assertEqual(hc.clients, windows)
        self.assertEqual([m['activeWorkspace']['id'] for m in hc.monitors], [1, 2])
        self.assert_atomic_rebuild(hc, saved)

    def test_atomic_close_preserves_fullscreen_and_pin_states(self):
        for modes in ([1, 1], [2, 2], [2, 0]):
            with self.subTest(modes=modes):
                windows = [dict(self.clients[0], fullscreen=modes[0], fullscreenClient=modes[1]),
                           dict(self.clients[1], pinned=True)]
                hc = CountingZoomHyprctl(windows, [dict(navigating=False, zoom=1)])
                hc.clients[0].update(floating=True, fullscreen=0, fullscreenClient=0)
                saved = packet(windows)
                self.path.write_text(json.dumps(saved))
                state.execute(hc, 'leave', self.path)
                self.assertEqual(hc.clients, windows)
                self.assertEqual(hc.commands.count(('pin', 'address:0xb')), 2)
                self.assertNotIn(('pin', 'address:0xa'), hc.commands)
                self.assert_atomic_rebuild(hc, saved)

    def test_omitted_post_close_detachment_or_monitor_repair_requires_slow_path(self):
        for omitted in ('detachment', 'monitors'):
            with self.subTest(omitted=omitted):
                hc = CountingZoomHyprctl(self.clients, [dict(navigating=False, zoom=1)])
                hc.clients[0]['floating'] = True
                saved = packet(self.clients)
                other = dict(MONITOR, id=1, name='OTHER', focused=False,
                             activeWorkspace=dict(id=2, name='2'))
                saved['monitors'].append(other)
                hc.monitors = copy.deepcopy(saved['monitors'])
                self.path.write_text(json.dumps(saved))
                batch = hc.batch
                def omit(commands):
                    if ('spatialoverview:overview', 'off all') in commands and len(commands) > 1:
                        if omitted == 'detachment':
                            commands = [c for c in commands if c != ('setfloating', 'address:0xa')]
                        else:
                            first = next(i for i in range(1, len(commands)) if commands[i][0] != 'keyword')
                            commands = commands[:first]+commands[first+5:]
                    batch(commands)
                with patch.object(hc, 'batch', side_effect=omit), \
                     contextlib.redirect_stderr(io.StringIO()) as stderr:
                    state.execute(hc, 'leave', self.path)
                self.assertIn('atomic restore needs multi-step repair', stderr.getvalue())
                self.assertGreater(len(hc.batches), 1)
                state.Restore(hc, saved).verify()

    def test_atomic_transport_splits_only_at_argv_limit_and_preserves_order(self):
        result = type('Result', (), dict(returncode=0, stdout='ok', stderr=''))()
        commands = [('spatialoverview:overview', 'off all')]
        commands += [('focuswindow', 'address:0xa')]*6000
        commands += [('movecursor', '4173 812')]
        with patch.object(state.subprocess, 'run', return_value=result) as run, \
             contextlib.redirect_stderr(io.StringIO()) as stderr:
            state.Hyprctl('offline-instance').batch(commands)
        self.assertEqual(run.call_count, 2)
        self.assertIn('requires 2 batch calls', stderr.getvalue())
        parts = [call.args[0][-1] for call in run.call_args_list]
        limit = min(32*state.os.sysconf('SC_PAGE_SIZE')-1, state.os.sysconf('SC_ARG_MAX')//2)
        self.assertTrue(all(len(part.encode()) <= limit for part in parts))
        self.assertEqual('; '.join(parts), '; '.join('dispatch '+name+' '+arg for name, arg in commands))

    def test_atomic_leave_recovers_marker_and_original_options_after_kill(self):
        for native_options_recorded in (False, True):
            with self.subTest(native_options_recorded=native_options_recorded):
                hc = CountingZoomHyprctl(self.clients, [dict(navigating=False, zoom=1)])
                hc.options.update({ANIMATIONS: 0, REMEMBER: 0})
                hc.clients[0]['floating'] = True
                self.path.write_text(json.dumps(packet(self.clients)))
                self.journal.write_text(json.dumps({REMEMBER: 1, AUTO_PLACE: 7, ANIMATIONS: 1}))
                self.marker.write_text(json.dumps({'group:auto_group': 1}) if native_options_recorded else '')
                if native_options_recorded:
                    hc.options['group:auto_group'] = 0
                state.execute(hc, 'toggle', self.path)
                self.assertEqual(hc.clients, self.clients)
                self.assertEqual(hc.options[ANIMATIONS], 1)
                self.assertEqual(hc.options[AUTO_PLACE], 7)
                self.assertEqual(hc.options.get('group:auto_group', 1), 1)
                self.assertFalse(self.path.exists())
                self.assertFalse(self.marker.exists())
                self.assertFalse(self.journal.exists())

    def test_real_dry_transport_prints_atomic_plan_without_mutation(self):
        fake = ZoomHyprctl(self.clients)
        fake.clients[0]['floating'] = True
        hc = state.Hyprctl(fake.instance, dry=True)
        original = self.path.read_text()
        with patch.object(hc, 'query', side_effect=fake.query), \
             patch.object(state.subprocess, 'run', side_effect=AssertionError('dry mutation')), \
             patch.object(state.time, 'sleep', side_effect=AssertionError('dry wait')), \
             contextlib.redirect_stdout(io.StringIO()) as stdout:
            state.execute(hc, 'leave', self.path)
        batches = [state.shlex.split(line)[-1] for line in stdout.getvalue().splitlines() if '--batch' in line]
        self.assertEqual(len(batches), 2)  # zoom plan followed by one atomic restore plan
        self.assertTrue(batches[-1].startswith('dispatch spatialoverview:overview off all; '))
        self.assertTrue(batches[-1].endswith('dispatch movecursor 4173 812'))
        self.assertNotIn('toggle all', batches[-1])
        self.assertEqual(self.path.read_text(), original)
        self.assertFalse(self.marker.exists())
        self.assertFalse(self.journal.exists())
        self.assertTrue(fake.clients[0]['floating'])

    def test_atomic_revive_handles_specials_that_survive_workspace_switches(self):
        for closes_special in (False, True):
            with self.subTest(closes_special=closes_special):
                hc = CountingZoomHyprctl(self.clients, [dict(navigating=False, zoom=1)])
                saved = packet(self.clients)
                saved['monitors'][0]['specialWorkspace'] = dict(id=-99, name='special:notes')
                empty = dict(MONITOR, id=1, name='EMPTY', focused=False,
                             activeWorkspace=dict(id=2, name='2'))
                saved['monitors'].append(copy.deepcopy(empty))
                hc.monitors = copy.deepcopy(saved['monitors'])
                hc.monitors[1]['activeWorkspace'] = dict(id=9, name='9')
                self.path.write_text(json.dumps(saved))
                batch = hc.batch
                def switch(commands):
                    batch(commands)
                    if closes_special:
                        # FakeHyprctl preserves special workspaces by default.
                        # Replay their independent visibility for close-on-switch compositors.
                        specials = {m['name']: saved['monitors'][i]['specialWorkspace']['name']
                                    for i, m in enumerate(hc.monitors)}
                        focused = 'TEST'
                        for name, arg in commands:
                            if name == 'focusmonitor':
                                focused = arg
                            elif name == 'workspace':
                                specials[focused] = ''
                            elif name == 'togglespecialworkspace':
                                specials[focused] = '' if specials[focused] == 'special:'+arg else 'special:'+arg
                        for m in hc.monitors:
                            m['specialWorkspace'] = (dict(id=-99, name=specials[m['name']])
                                if specials[m['name']] else dict(id=0, name=''))
                with patch.object(hc, 'batch', side_effect=switch):
                    state.execute(hc, 'leave', self.path)
                self.assertEqual(len(hc.batches), 1)
                self.assertEqual(hc.monitors[0]['specialWorkspace'], dict(id=-99, name='special:notes'))
                self.assertEqual(hc.options[ANIMATIONS], 1)

    def check_atomic_group_rebuild(self, floating):
        group = ['0xa', '0xb']
        windows = [client('0xa', 3012, 509, 600, 979, grouped=group, acceptsInput=True),
                   client('0xb', 3012, 509, 600, 979, grouped=group, acceptsInput=False)]
        for c in windows:
            c['floating'] = floating
        if floating:
            windows.append(client('0xe', 4000, 700, 200, 150, floating=True))
        new = client('0xc', 3012, 509, 600, 979, floating=floating,
                     grouped=group+['0xc'], acceptsInput=False)
        class GroupCompositor(ZoomHyprctl):
            def __init__(self):
                super().__init__(windows+[new], [dict(navigating=False, zoom=1)])
                self.calls = []
                for c in self.clients:
                    if c['address'] in group+['0xc']:
                        c['grouped'] = group+['0xc']

            def batch(self, commands):
                self.calls.append(list(commands))
                for name, arg in commands:
                    super().batch([(name, arg)])
                    active = next((c for c in self.clients if c['address'] == self.active), None)
                    if name == 'togglegroup':
                        members = active['grouped'][:]
                        for c in self.clients:
                            if c['address'] in members:
                                c['grouped'] = []
                        if not members:
                            active['grouped'] = [active['address']]
                    elif name == 'moveintogroup':
                        root = next(c for c in self.clients if c != active and c['grouped'])
                        members = root['grouped']+[active['address']]
                        for c in self.clients:
                            if c['address'] in members:
                                c['grouped'] = members[:]
                                c['acceptsInput'] = c == active
                    elif name in ('setfloating', 'settiled'):
                        target = next(c for c in self.clients if c['address'] == arg.removeprefix('address:'))
                        for c in self.clients:
                            if c['address'] in target['grouped']:
                                c['floating'] = name == 'setfloating'
                    elif name == 'focuswindow' and active['grouped']:
                        for c in self.clients:
                            if c['address'] in active['grouped']:
                                c['acceptsInput'] = c == active
        hc = GroupCompositor()
        saved = packet(windows)
        if floating:
            saved['activewindow'] = dict(address='0xe')
        self.path.write_text(json.dumps(saved))
        state.execute(hc, 'leave', self.path)
        self.assertEqual(len(hc.calls), 1)
        # Close re-tiles the newly added canvas member. With no entry snapshot
        # for it, both planners retain it as a native tile after detaching it.
        self.assertFalse(hc.clients[-1]['floating'])
        self.assertEqual(hc.clients[-1]['grouped'], [])
        self.assertEqual(hc.clients[:-1], windows)
        self.assertEqual(hc.options[ANIMATIONS], 1)
        self.assert_atomic_rebuild(hc, saved)

    def test_atomic_group_rebuild_reattaches_new_native_members(self):
        self.check_atomic_group_rebuild(floating=False)

    def test_atomic_floating_group_rebuild_restores_tab_before_unrelated_focus(self):
        self.check_atomic_group_rebuild(floating=True)

    def test_zoom_finishes_on_every_screen_before_animations_off_and_close(self):
        hc = ZoomHyprctl(self.clients)
        hc.zoom_frames = [[dict(navigating=True, zoom=.998)],
                          [dict(navigating=False, zoom=.994)],
                          [dict(navigating=False, zoom=.999), dict(navigating=False, zoom=.99)],
                          [dict(navigating=False, zoom=.999), dict(navigating=False, zoom=1)],
                          [dict(navigating=False, zoom=1), dict(navigating=False, zoom=1)]]
        batch = hc.batch
        def checked(commands):
            if ('spatialoverview:overview', 'toggle all') in commands:
                self.assertTrue(self.marker.exists())
            if ('spatialoverview:overview', 'off all') in commands:
                self.assertEqual(json.loads(self.journal.read_text())[ANIMATIONS], 1)
                self.assertEqual(hc.view, hc.zoom_frames[-1] if hc.zoom_frames else
                                 [dict(navigating=False, zoom=1), dict(navigating=False, zoom=1)])
            batch(commands)
        with patch.object(hc, 'batch', side_effect=checked), patch.object(state.time, 'sleep') as sleep:
            state.execute(hc, 'leave', self.path)
        toggle = hc.events.index(('spatialoverview:overview', 'toggle all'))
        disabled = hc.events.index(('keyword', ANIMATIONS, 0))
        close = hc.events.index(('spatialoverview:overview', 'off all'))
        self.assertLess(toggle, disabled)
        self.assertLess(disabled, close)
        self.assertEqual(sleep.call_count, 4)
        self.assertTrue(all(.015 <= call.args[0] <= .02 for call in sleep.call_args_list))
        self.assertEqual(hc.commands.count(('spatialoverview:overview', 'toggle all')), 1)
        self.assertEqual(hc.events[-1], ('keyword', ANIMATIONS, 1))
        self.assertFalse(self.path.exists())

    def test_zoom_tail_is_not_cut_before_the_plugin_reports_exactly_one(self):
        # The plugin fades distortion, dim and minimap with the zoom; .995 still showed a 5 px hop.
        hc = ZoomHyprctl(self.clients)
        hc.zoom_frames = [[dict(navigating=False, zoom=zoom)] for zoom in (.995, .997, .999, 1)]
        with patch.object(state.time, 'sleep') as sleep:
            state.execute(hc, 'leave', self.path)
        disabled = hc.events.index(('keyword', ANIMATIONS, 0))
        views = [event[1][0]['zoom'] for event in hc.events[:disabled] if event[0] == 'view']
        self.assertEqual(views[-4:], [.995, .997, .999, 1])
        self.assertEqual(sleep.call_count, 3)
        self.assertLess(disabled, hc.events.index(('spatialoverview:overview', 'off all')))
        self.assertEqual(hc.options[ANIMATIONS], 1)
        self.assertFalse(self.path.exists())

    def test_at_100_percent_or_closed_never_toggles(self):
        for closed in (False, True):
            with self.subTest(closed=closed):
                hc = ZoomHyprctl(self.clients, [dict(navigating=False, zoom=1)])
                hc.screens = 0 if closed else 1
                self.path.write_text(json.dumps(packet(self.clients)))
                state.execute(hc, 'leave', self.path)
                self.assertNotIn(('spatialoverview:overview', 'toggle all'), hc.commands)
                self.assertEqual(hc.options[ANIMATIONS], 1)

    def test_zoom_timeout_warns_and_continues_with_a_bounded_wait(self):
        hc = ZoomHyprctl(self.clients)
        hc.zoom_frames = []
        with patch.object(state.time, 'monotonic', side_effect=[0, 0, 1, 2, 3, 4, 5]), \
             patch.object(state.time, 'sleep') as sleep, contextlib.redirect_stderr(io.StringIO()) as stderr:
            state.execute(hc, 'leave', self.path)
        self.assertIn('warning', stderr.getvalue())
        self.assertIn('zoom', stderr.getvalue())
        self.assertLessEqual(sleep.call_count, 4)
        self.assertEqual(hc.options[ANIMATIONS], 1)
        self.assertFalse(self.path.exists())

    def test_disappearing_screens_stop_zoom_wait_without_reopening(self):
        hc = ZoomHyprctl(self.clients)
        hc.zoom_frames = [[]]
        with patch.object(state.time, 'sleep', side_effect=AssertionError('unnecessary wait')):
            state.execute(hc, 'leave', self.path)
        self.assertEqual(hc.commands.count(('spatialoverview:overview', 'toggle all')), 1)
        self.assertEqual(hc.options[ANIMATIONS], 1)

    def test_rebuild_and_verification_failures_restore_animations_after_pointer(self):
        for method in ('run', 'verify'):
            with self.subTest(method=method):
                hc = ZoomHyprctl(self.clients)
                self.path.write_text(json.dumps(packet(self.clients)))
                with patch.object(state.Restore, method, side_effect=RuntimeError('rebuild failed')):
                    with self.assertRaisesRegex(RuntimeError, 'rebuild failed'):
                        state.execute(hc, 'leave', self.path)
                self.assertEqual(hc.options[ANIMATIONS], 1)
                self.assertEqual(hc.events[-1], ('keyword', ANIMATIONS, 1))
                self.assertLess(hc.events.index(('movecursor', '4173 812')),
                                hc.events.index(('keyword', ANIMATIONS, 1)))
                self.assertTrue(self.path.exists())

    def test_reopened_retry_keeps_animations_off_and_restores_pointer_once_at_end(self):
        hc = ZoomHyprctl(self.clients)
        run = state.Restore.run
        attempts = []
        def reopen(restore, before_focus):
            self.assertEqual(hc.options[ANIMATIONS], 0)
            attempts.append(1)
            if len(attempts) == 1:
                hc.screens = 1
                hc.batch([('movecursor', '123 456')])
                before_focus()
            run(restore, before_focus)
        with patch.object(state.Restore, 'run', reopen):
            state.execute(hc, 'leave', self.path)
        self.assertEqual(len(attempts), 2)
        self.assertEqual(hc.commands.count(('movecursor', '4173 812')), 1)
        self.assertEqual(hc.cursor, dict(x=4173, y=812))
        self.assertEqual(hc.options[ANIMATIONS], 1)

    def test_killed_leave_journal_preserves_first_original_on_next_press(self):
        hc = ZoomHyprctl(self.clients)
        hc.screens = 0
        hc.options.update({ANIMATIONS: 0, REMEMBER: 0})
        original = {REMEMBER: 1, AUTO_PLACE: 7, ANIMATIONS: 1}
        self.journal.write_text(json.dumps(original))
        self.assertEqual(state.read_canvas_options(self.journal), original)
        batch = hc.batch
        def checked(commands):
            if ('spatialoverview:overview', 'off all') in commands:
                self.assertEqual(json.loads(self.journal.read_text()), original)
            batch(commands)
        with patch.object(hc, 'batch', side_effect=checked):
            state.execute(hc, 'toggle', self.path)
        self.assertEqual(hc.options[ANIMATIONS], 1)
        self.assertEqual(hc.options[AUTO_PLACE], 7)
        self.assertFalse(self.path.exists())
        self.assertFalse(self.journal.exists())

    def test_stale_or_missing_snapshot_enter_restores_killed_animation_setting(self):
        for missing in (False, True):
            with self.subTest(missing=missing):
                hc = ZoomHyprctl(self.clients)
                hc.screens = 0
                hc.options[ANIMATIONS] = 0
                if missing:
                    self.path.unlink(missing_ok=True)
                self.journal.write_text(json.dumps({REMEMBER: 1, AUTO_PLACE: 1, ANIMATIONS: 1}))
                state.execute(hc, 'enter', self.path)
                self.assertEqual(hc.options[ANIMATIONS], 1)
                self.assertNotIn(ANIMATIONS, json.loads(self.journal.read_text()))
                self.assertLess(hc.events.index(('keyword', ANIMATIONS, 1)),
                                hc.events.index(('query', 'clients')))

    def test_originally_disabled_animations_stay_disabled(self):
        hc = ZoomHyprctl(self.clients)
        hc.options[ANIMATIONS] = 0
        state.execute(hc, 'leave', self.path)
        self.assertEqual(hc.options[ANIMATIONS], 0)
        self.assertEqual(hc.events[-1], ('keyword', ANIMATIONS, 0))
        self.assertNotIn(('keyword', ANIMATIONS, 1), hc.events)

    def test_interrupt_unwinds_pointer_and_animations_and_leaves_retry_marker(self):
        for interruption in (KeyboardInterrupt, SystemExit):
            with self.subTest(interruption=interruption):
                hc = ZoomHyprctl(self.clients)
                self.path.write_text(json.dumps(packet(self.clients)))
                with patch.object(state.Restore, 'run', side_effect=interruption):
                    with self.assertRaises(interruption):
                        state.execute(hc, 'leave', self.path)
                self.assertEqual(hc.cursor, dict(x=4173, y=812))
                self.assertEqual(hc.options[ANIMATIONS], 1)
                self.assertTrue(self.marker.exists())
                self.assertTrue(self.path.exists())

    def test_pre_close_native_state_still_rebuilds_after_synchronous_close(self):
        hc = ZoomHyprctl(self.clients)
        state.execute(hc, 'leave', self.path)
        self.assert_atomic_rebuild(hc, packet(self.clients))

    def test_cursor_and_focus_share_rebuild_batches_before_split_checks(self):
        hc = ZoomHyprctl(self.clients)
        hc.clients[0]['floating'] = True
        state.execute(hc, 'leave', self.path)
        self.assertTrue(any(('settiled', 'address:0xa') in commands for commands in hc.batches))
        self.assertTrue(any(('movecursor', '3312 973') in commands and
                            ('focuswindow', 'address:0xa') in commands for commands in hc.batches))

    def test_disable_precedes_atomic_close_and_restore(self):
        hc = ZoomHyprctl(self.clients)
        state.execute(hc, 'leave', self.path)
        self.assertLess(hc.events.index(('keyword', ANIMATIONS, 0)),
                        hc.events.index(('spatialoverview:overview', 'off all')))
        self.assertEqual(hc.batches[-1][0], ('spatialoverview:overview', 'off all'))
        self.assertEqual(hc.batches[-1][-1], ('movecursor', '4173 812'))

    def test_failed_animation_restore_retains_original_for_next_leave(self):
        hc = ZoomHyprctl(self.clients)
        keyword = hc.keyword
        def fail(name, value):
            if name == ANIMATIONS and value == 1:
                raise RuntimeError('animation restore refused')
            keyword(name, value)
        with patch.object(hc, 'keyword', side_effect=fail):
            with self.assertRaisesRegex(RuntimeError, 'animation restore refused'):
                state.execute(hc, 'leave', self.path)
        self.assertEqual(json.loads(self.journal.read_text())[ANIMATIONS], 1)
        self.assertTrue(self.path.exists())
        state.execute(hc, 'toggle', self.path)
        self.assertEqual(hc.options[ANIMATIONS], 1)
        self.assertFalse(self.path.exists())

    def test_invalid_snapshot_restores_prior_animation_journal_without_zoom(self):
        hc = ZoomHyprctl(self.clients)
        hc.options[ANIMATIONS] = 0
        self.path.write_text('invalid')
        self.journal.write_text(json.dumps({REMEMBER: 1, AUTO_PLACE: 7, ANIMATIONS: 1}))
        state.execute(hc, 'leave', self.path)
        self.assertNotIn(('spatialoverview:overview', 'toggle all'), hc.commands)
        self.assertEqual(hc.options[ANIMATIONS], 1)

    def test_dry_leave_reports_zoom_and_animation_work_without_writing_or_waiting(self):
        hc = ZoomHyprctl(self.clients)
        hc.dry = True
        original = {REMEMBER: 1, AUTO_PLACE: 7, ANIMATIONS: 1}
        self.journal.write_text(json.dumps(original))
        with patch.object(state.time, 'sleep', side_effect=AssertionError('dry wait')), \
             contextlib.redirect_stderr(io.StringIO()) as stderr:
            state.execute(hc, 'leave', self.path)
        self.assertIn('would wait', stderr.getvalue())
        self.assertIn('would journal animations:enabled=1', stderr.getvalue())
        self.assertIn('would restore animations:enabled to 1', stderr.getvalue())
        self.assertEqual(json.loads(self.journal.read_text()), original)
        self.assertFalse(self.marker.exists())
        self.assertTrue(self.path.exists())

    def test_dry_leave_without_journal_reports_original_animation_restore(self):
        hc = ZoomHyprctl(self.clients)
        hc.dry = True
        with contextlib.redirect_stderr(io.StringIO()) as stderr:
            state.execute(hc, 'leave', self.path)
        self.assertIn('would restore animations:enabled to 1', stderr.getvalue())
        self.assertEqual(hc.options[ANIMATIONS], 1)
        self.assertFalse(self.journal.exists())

    def test_leave_restores_current_pointer_once_even_with_saved_split_monitor_focus(self):
        hc = ZoomHyprctl(self.clients)
        hc.active = '0xb'
        other = dict(MONITOR, id=1, name='OTHER', x=1920, y=0, focused=True,
                     activeWorkspace=dict(id=2, name='2'))
        saved = packet(self.clients)
        saved['monitors'][0]['focused'] = False
        saved['monitors'].append(copy.deepcopy(other))
        saved['cursor'] = [2400, 10]
        hc.monitors = copy.deepcopy(saved['monitors'])
        hc.cursor = dict(x=2500, y=100)
        self.path.write_text(json.dumps(saved))
        state.execute(hc, 'leave', self.path)
        self.assertEqual(hc.cursor, dict(x=2500, y=100))
        self.assertEqual(hc.commands.count(('movecursor', '2500 100')), 1)
        self.assertNotIn(('movecursor', '2400 10'), hc.commands)

    def test_partial_floating_finish_failure_still_restores_later_windows(self):
        windows = [dict(c, floating=True) for c in self.clients]
        hc = ZoomHyprctl(windows)
        for c in hc.clients:
            c['floating'] = False
        batch = hc.batch
        failed = False
        def fail(commands):
            nonlocal failed
            if ('setfloating', 'address:0xa') in commands and not failed:
                failed = True
                batch(commands[:1])
                raise RuntimeError('partial floating restore failure')
            batch(commands)
        with patch.object(hc, 'batch', side_effect=fail):
            restore = state.Restore(hc, packet(windows))
            restore.finish()
        self.assertTrue(restore.errors)
        self.assertTrue(all(c['floating'] for c in hc.clients))

    def test_zoom_query_transport_timeout_is_nonfatal(self):
        hc = ZoomHyprctl(self.clients)
        query = hc.query
        def timeout(name, *args, **kwargs):
            if name == 'spatialoverview' and hc.zooming and hc.screens:
                self.assertGreater(kwargs['timeout'], 0)
                self.assertLessEqual(kwargs['timeout'], 4)
                raise state.subprocess.TimeoutExpired('offline zoom query', kwargs['timeout'])
            return query(name, *args, **kwargs)
        with patch.object(hc, 'query', side_effect=timeout), contextlib.redirect_stderr(io.StringIO()) as stderr:
            state.execute(hc, 'leave', self.path)
        self.assertIn('warning: canvas zoom', stderr.getvalue())
        self.assertEqual(hc.options[ANIMATIONS], 1)
        self.assertFalse(self.path.exists())

    def test_already_pinned_floating_window_recovers_post_close_geometry(self):
        windows = [dict(self.clients[1], pinned=True)]
        hc = ZoomHyprctl(windows)
        self.path.write_text(json.dumps(packet(windows)))
        state.execute(hc, 'leave', self.path)
        self.assertIn(('setfloating', 'address:0xb'), hc.commands)
        self.assertEqual(hc.clients, windows)
        self.assertTrue(hc.clients[0]['pinned'])

    def test_animation_restore_still_runs_if_plugin_option_cleanup_is_interrupted(self):
        hc = ZoomHyprctl(self.clients)
        keyword = hc.keyword
        def interrupted(name, value):
            if name == AUTO_PLACE and value == 1:
                raise KeyboardInterrupt
            keyword(name, value)
        with patch.object(hc, 'keyword', side_effect=interrupted):
            with self.assertRaises(KeyboardInterrupt):
                state.execute(hc, 'leave', self.path)
        self.assertEqual(hc.options[ANIMATIONS], 1)

    def test_native_restore_options_are_set_in_one_batch(self):
        hc = ZoomHyprctl(self.clients)
        state.execute(hc, 'leave', self.path)
        self.assertTrue(any(('keyword', 'dwindle:smart_resizing 0') in commands and
                            ('keyword', 'group:auto_group 0') in commands for commands in hc.batches))

    def test_mixed_keyword_dispatch_batch_uses_real_hyprctl_syntax(self):
        result = type('Result', (), dict(returncode=0, stdout='ok\nok', stderr=''))()
        with patch.object(state.subprocess, 'run', return_value=result) as run:
            state.Hyprctl('offline-instance').batch([('keyword', ANIMATIONS+' 0'),
                                                    ('spatialoverview:overview', 'off all')])
        self.assertEqual(run.call_args.args[0], ['hyprctl', '-i', 'offline-instance', '--batch',
                         'keyword animations:enabled 0; dispatch spatialoverview:overview off all'])

    def test_dry_failed_leave_keeps_existing_retry_marker(self):
        hc = ZoomHyprctl(self.clients)
        hc.dry = True
        self.marker.write_text('retry evidence')
        with patch.object(state.Restore, 'run', side_effect=RuntimeError('dry restore failure')):
            with self.assertRaisesRegex(RuntimeError, 'dry restore failure'):
                state.execute(hc, 'leave', self.path)
        self.assertEqual(self.marker.read_text(), 'retry evidence')
        self.assertTrue(self.path.exists())

    def test_partial_finish_flush_does_not_toggle_pin_twice_or_skip_native_repair(self):
        windows = [dict(self.clients[0], floating=True, pinned=True),
                   dict(self.clients[1], floating=False)]
        hc = ZoomHyprctl(windows)
        hc.clients[0]['pinned'] = False
        hc.clients[1]['floating'] = True
        batch = hc.batch
        failed = False
        def fail(commands):
            nonlocal failed
            batch(commands)
            if ('pin', 'address:0xa') in commands and not failed:
                failed = True
                raise RuntimeError('partial finish flush failure')
        with patch.object(hc, 'batch', side_effect=fail):
            restore = state.Restore(hc, packet(windows))
            restore.finish()
        self.assertTrue(restore.errors)
        self.assertTrue(hc.clients[0]['pinned'])
        self.assertFalse(hc.clients[1]['floating'])


# polish: exercise optional glass release, frame ordering and journal recovery offline.
GLASS = 'plugin:hyprglass:manage_window_blur'
OPACITY = 'plugin:hyprglass:glass_opacity'


class CanvasPolish(unittest.TestCase):
    def setUp(self):
        self.clients = [client('0xa', 3012, 459, 600, 1029),
                        client('0xb', 3700, 500, 400, 300, floating=True)]
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.path = pathlib.Path(directory)/'snapshot.json'
        self.journal = pathlib.Path(str(self.path)+'.options')
        self.enterContext(contextlib.redirect_stderr(io.StringIO()))
        self.sleep = self.enterContext(patch.object(state.time, 'sleep'))

    def test_changed_glass_is_journalled_before_release_and_waits_before_open(self):
        hc = CanvasHyprctl(self.clients)
        hc.options[GLASS] = 1
        keyword = hc.keyword
        def checked(name, value):
            if name == GLASS and value == 0:
                self.assertEqual(json.loads(self.journal.read_text())[GLASS], 1)
            keyword(name, value)
        self.sleep.side_effect = lambda seconds: hc.events.append(('sleep', seconds))
        with patch.object(hc, 'keyword', side_effect=checked):
            state.execute(hc, 'enter', self.path)
        self.assertEqual(hc.options[GLASS], 0)
        self.sleep.assert_called_once_with(.15)
        release = hc.events.index(('keyword', GLASS, 0))
        frame = hc.events.index(('sleep', .15))
        opening = hc.events.index(('spatialoverview:overview', 'toggle all'))
        self.assertLess(release, frame)
        self.assertLess(frame, opening)
        self.assertFalse(any(('keyword', GLASS+' 0') in batch for batch in hc.batches))

    def test_unchanged_glass_has_no_keyword_or_frame_wait(self):
        hc = CanvasHyprctl(self.clients)
        hc.options[GLASS] = 0
        state.execute(hc, 'enter', self.path)
        self.sleep.assert_not_called()
        self.assertNotIn(GLASS, json.loads(self.journal.read_text()))
        self.assertNotIn(('keyword', GLASS, 0), hc.events)
        state.execute(hc, 'leave', self.path)
        self.assertEqual(hc.options[GLASS], 0)

    def test_missing_glass_does_not_abort_or_print_warning(self):
        hc = CanvasHyprctl(self.clients)
        with contextlib.redirect_stderr(io.StringIO()) as stderr:
            state.execute(hc, 'enter', self.path)
        self.assertEqual(hc.screens, 1)
        self.assertNotIn(GLASS, json.loads(self.journal.read_text()))
        self.assertNotIn('no such option', stderr.getvalue())
        self.sleep.assert_not_called()

    def test_missing_glass_json_field_does_not_abort(self):
        hc = CanvasHyprctl(self.clients)
        query = hc.query
        def missing(name, *args, **kwargs):
            return {'error': 'no such option'} if args == (GLASS,) else query(name, *args, **kwargs)
        with patch.object(hc, 'query', side_effect=missing):
            state.execute(hc, 'enter', self.path)
        self.assertEqual(hc.screens, 1)
        self.sleep.assert_not_called()

    def test_dry_glass_enter_does_not_sleep_or_write_journal(self):
        hc = CanvasHyprctl(self.clients)
        hc.options[GLASS] = 1
        hc.dry = True
        state.execute(hc, 'enter', self.path)
        self.sleep.assert_not_called()
        self.assertFalse(self.journal.exists())

    def test_leave_restores_glass_after_zoom_and_verified_rebuild(self):
        hc = ZoomHyprctl(self.clients)
        hc.options[GLASS] = 0
        self.path.write_text(json.dumps(packet(self.clients)))
        self.journal.write_text(json.dumps({REMEMBER: 1, AUTO_PLACE: 1, GLASS: 1}))
        state.execute(hc, 'leave', self.path)
        self.assertEqual(hc.options[GLASS], 1)
        restored = hc.events.index(('keyword', GLASS, 1))
        self.assertLess(hc.events.index(('view', [dict(navigating=False, zoom=1)])), restored)
        self.assertLess(hc.events.index(('spatialoverview:overview', 'off all')), restored)
        self.assertGreater(restored, max(i for i, event in enumerate(hc.events) if event == ('query', 'clients')))
        self.assertFalse(self.journal.exists())

    def test_journal_without_snapshot_recovers_glass_before_new_entry(self):
        hc = CanvasHyprctl(self.clients)
        hc.options[GLASS] = 0
        self.journal.write_text(json.dumps({REMEMBER: 1, AUTO_PLACE: 1, GLASS: 1}))
        state.execute(hc, 'enter', self.path)
        self.assertLess(hc.events.index(('keyword', GLASS, 1)), hc.events.index(('query', 'clients')))
        self.assertEqual(json.loads(self.journal.read_text())[GLASS], 1)
        self.assertEqual(hc.options[GLASS], 0)

    # polish: crash evidence must not make an absent plugin mandatory on the next entry.
    def test_journal_with_unloaded_glass_still_allows_entry(self):
        hc = CanvasHyprctl(self.clients)
        self.journal.write_text(json.dumps({REMEMBER: 1, AUTO_PLACE: 1, GLASS: 1}))
        state.execute(hc, 'enter', self.path)
        self.assertEqual(hc.screens, 1)
        self.assertNotIn(GLASS, hc.options)
        self.assertNotIn(GLASS, json.loads(self.journal.read_text()))
        self.sleep.assert_not_called()

    def test_failed_glass_restore_keeps_journal_for_retry(self):
        hc = CanvasHyprctl(self.clients)
        hc.options[GLASS] = 0
        self.journal.write_text(json.dumps({REMEMBER: 1, AUTO_PLACE: 1, GLASS: 1}))
        keyword = hc.keyword
        def fail(name, value):
            if name == GLASS:
                raise RuntimeError('glass restore refused')
            keyword(name, value)
        with patch.object(hc, 'keyword', side_effect=fail):
            with self.assertRaisesRegex(RuntimeError, 'glass restore refused'):
                state.execute(hc, 'leave', self.path)
        self.assertEqual(json.loads(self.journal.read_text())[GLASS], 1)
        state.execute(hc, 'leave', self.path)
        self.assertEqual(hc.options[GLASS], 1)
        self.assertFalse(self.journal.exists())

    def test_failed_open_restores_glass_even_after_toggle_started(self):
        hc = CanvasHyprctl(self.clients)
        hc.options[GLASS] = 1
        batch = hc.batch
        def fail(commands):
            batch(commands)
            if ('spatialoverview:overview', 'toggle all') in commands:
                raise RuntimeError('open failed after dispatch')
        with patch.object(hc, 'batch', side_effect=fail):
            with self.assertRaisesRegex(RuntimeError, 'open failed after dispatch'):
                state.execute(hc, 'enter', self.path)
        self.assertEqual(hc.options[GLASS], 1)
        self.assertEqual(json.loads(self.journal.read_text())[GLASS], 1)

    def test_interrupted_option_cleanup_still_restores_glass(self):
        hc = CanvasHyprctl(self.clients)
        hc.options[GLASS] = 0
        self.journal.write_text(json.dumps({REMEMBER: 1, AUTO_PLACE: 1, GLASS: 1}))
        keyword = hc.keyword
        def interrupt(name, value):
            if name == AUTO_PLACE:
                raise KeyboardInterrupt
            keyword(name, value)
        with patch.object(hc, 'keyword', side_effect=interrupt):
            with self.assertRaises(KeyboardInterrupt):
                state.execute(hc, 'leave', self.path)
        self.assertEqual(hc.options[GLASS], 1)


    # polish: the glass switch hides in an opacity fade; the configured opacity is journalled.
    def glass_hc(self, kind, glass, opacity, configured=None):
        hc = kind(self.clients)
        hc.options.update({GLASS: glass, OPACITY: opacity})
        if configured is not None:
            self.journal.write_text(json.dumps({REMEMBER: 1, AUTO_PLACE: 1, GLASS: 1, OPACITY: configured}))
        return hc

    def opacities(self, hc):
        return [event[2] for event in hc.events if event[:2] == ('keyword', OPACITY)]

    def test_enter_fades_opacity_down_before_release_and_restores_it(self):
        hc = self.glass_hc(CanvasHyprctl, 1, .9)
        keyword = hc.keyword
        def checked(name, value):
            if name == OPACITY:
                self.assertEqual(json.loads(self.journal.read_text())[OPACITY], .9)
            keyword(name, value)
        with patch.object(hc, 'keyword', side_effect=checked):
            state.execute(hc, 'enter', self.path)
        release = hc.events.index(('keyword', GLASS, 0))
        ramp = [event[2] for event in hc.events[:release] if event[:2] == ('keyword', OPACITY)]
        self.assertEqual(len(ramp), state.GLASS_FADE_STEPS)
        self.assertEqual(ramp, sorted(ramp, reverse=True))
        self.assertLess(ramp[0], .9)
        self.assertEqual(ramp[-1], state.GLASS_MATCH)
        self.assertEqual(hc.events[release+1], ('keyword', OPACITY, .9))
        self.assertEqual({call.args[0] for call in self.sleep.call_args_list},
                         {state.GLASS_FADE/state.GLASS_FADE_STEPS})
        self.assertLess(release+1, hc.events.index(('spatialoverview:overview', 'toggle all')))
        self.assertEqual(hc.options[OPACITY], .9)
        self.assertEqual(json.loads(self.journal.read_text())[OPACITY], .9)

    def test_leave_restores_glass_at_match_then_fades_to_configured_opacity(self):
        hc = self.glass_hc(ZoomHyprctl, 0, .9, configured=.9)
        self.path.write_text(json.dumps(packet(self.clients)))
        state.execute(hc, 'leave', self.path)
        restored = hc.events.index(('keyword', GLASS, 1))
        self.assertLess(hc.events.index(('keyword', OPACITY, state.GLASS_MATCH)), restored)
        ramp = [event[2] for event in hc.events[restored:] if event[:2] == ('keyword', OPACITY)]
        self.assertEqual(len(ramp), state.GLASS_FADE_STEPS)
        self.assertEqual(ramp, sorted(ramp))
        self.assertGreater(ramp[0], state.GLASS_MATCH)
        self.assertEqual(ramp[-1], .9)
        self.assertEqual(self.opacities(hc)[0], state.GLASS_MATCH)
        self.assertEqual((hc.options[GLASS], hc.options[OPACITY]), (1, .9))
        self.assertFalse(self.journal.exists())

    def test_opacity_configured_below_match_is_never_changed(self):
        hc = self.glass_hc(CanvasHyprctl, 1, .2)
        state.execute(hc, 'enter', self.path)
        state.execute(hc, 'leave', self.path)
        self.assertEqual(set(self.opacities(hc)), {.2})
        self.assertEqual((hc.options[GLASS], hc.options[OPACITY]), (1, .2))

    def test_killed_fade_is_recovered_from_journal_before_new_entry(self):
        hc = self.glass_hc(CanvasHyprctl, 1, .45, configured=.8)
        state.execute(hc, 'enter', self.path)
        self.assertLess(hc.events.index(('keyword', OPACITY, .8)), hc.events.index(('query', 'clients')))
        self.assertEqual(hc.options[OPACITY], .8)
        self.assertEqual(json.loads(self.journal.read_text())[OPACITY], .8)

    def test_killed_fade_is_recovered_from_journal_on_leave(self):
        hc = self.glass_hc(CanvasHyprctl, 0, .3, configured=.8)
        state.execute(hc, 'leave', self.path)
        self.assertEqual((hc.options[GLASS], hc.options[OPACITY]), (1, .8))
        self.assertFalse(self.journal.exists())

    def test_interrupted_fade_still_ends_at_configured_opacity(self):
        hc = self.glass_hc(CanvasHyprctl, 0, 1.0, configured=1.0)
        self.sleep.side_effect = [None, None, KeyboardInterrupt]
        with self.assertRaises(KeyboardInterrupt):
            state.execute(hc, 'leave', self.path)
        self.assertEqual((hc.options[GLASS], hc.options[OPACITY]), (1, 1.0))

    def test_failed_glass_restore_keeps_opacity_configured_and_journalled(self):
        hc = self.glass_hc(CanvasHyprctl, 0, 1.0, configured=1.0)
        keyword = hc.keyword
        def fail(name, value):
            if name == GLASS:
                raise RuntimeError('glass restore refused')
            keyword(name, value)
        with patch.object(hc, 'keyword', side_effect=fail):
            with self.assertRaisesRegex(RuntimeError, 'glass restore refused'):
                state.execute(hc, 'leave', self.path)
        self.assertEqual(hc.options[OPACITY], 1.0)
        self.assertEqual(json.loads(self.journal.read_text())[OPACITY], 1.0)

    def test_failed_open_restores_opacity(self):
        hc = self.glass_hc(CanvasHyprctl, 1, .9)
        batch = hc.batch
        def fail(commands):
            batch(commands)
            if ('spatialoverview:overview', 'toggle all') in commands:
                raise RuntimeError('open failed after dispatch')
        with patch.object(hc, 'batch', side_effect=fail):
            with self.assertRaisesRegex(RuntimeError, 'open failed after dispatch'):
                state.execute(hc, 'enter', self.path)
        self.assertEqual((hc.options[GLASS], hc.options[OPACITY]), (1, .9))

    def test_journalled_opacity_with_unloaded_glass_still_allows_entry(self):
        hc = CanvasHyprctl(self.clients)
        self.journal.write_text(json.dumps({REMEMBER: 1, AUTO_PLACE: 1, GLASS: 1, OPACITY: .9}))
        state.execute(hc, 'enter', self.path)
        self.assertEqual(hc.screens, 1)
        self.assertNotIn(OPACITY, hc.options)

    def test_dry_run_does_not_fade(self):
        hc = self.glass_hc(CanvasHyprctl, 1, .9)
        hc.dry = True
        state.execute(hc, 'enter', self.path)
        self.sleep.assert_not_called()
        self.assertEqual(self.opacities(hc), [state.GLASS_MATCH, .9])


class CanvasEnterBatchTests(unittest.TestCase):
    def test_skips_gone_windows_and_clamps_sizes(self):
        mon = dict(id=0, name='DP-1', x=0, y=0, width=1000, height=800, scale=1,
                   activeWorkspace=dict(id=1), specialWorkspace=dict(id=0))
        def win(addr, size):
            return dict(address=addr, mapped=True, floating=True, at=[10, 10], size=size,
                        workspace=dict(id=1, name='1'), monitor=0)
        saved = dict(monitors=[mon], clients=[win('0xa', [0, -5]), win('0xb', [300, 200])])
        current = {'0xa': win('0xa', [0, -5])}
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            commands = state.canvas_enter_commands(saved, current)
        self.assertEqual(err.getvalue().count('skipped 0xb'), 1)
        self.assertTrue(all('0xb' not in a for _, a in commands))
        self.assertIn(('resizewindowpixel', 'exact 20 20,address:0xa'), commands)


if __name__ == '__main__':
    unittest.main()
