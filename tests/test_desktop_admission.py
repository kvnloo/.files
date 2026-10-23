"""Tiny admission-only regressions: never start a real build or network transfer."""
import importlib.machinery
import pathlib
import os
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
fleet = importlib.machinery.SourceFileLoader('fleet_admission', str(ROOT/'scripts/fleet')).load_module()
classifier = importlib.machinery.SourceFileLoader('agent_classifier', str(ROOT/'scripts/agent-resource-classify')).load_module()

class Admission(unittest.TestCase):
    def setUp(self):
        self.n = fleet.registry()[1]['mbp']
        self.args = types.SimpleNamespace(node='mbp', cls=None, arch=None, tolerate=[], cmd=['true'], mem='1G')
        self.kn = {'mbp': {'conditions': {'Ready': 'True'}, 'unschedulable': False}}
        self.p = {'mem_available_mb': 10000, 'load1': 0, 'ncpu': 8, 'max_temp_c': 99, 'power': {}}

    def launch_rejected(self, probe, state):
        with tempfile.TemporaryDirectory() as td, \
             patch.object(fleet, 'registry', return_value=({}, {'mbp': self.n})), \
             patch.object(fleet, 'k8s_nodes', return_value=self.kn), \
             patch.object(fleet, 'probe', return_value=probe), \
             patch.object(fleet, 'STATE', pathlib.Path(td)), \
             patch.object(fleet.subprocess, 'run', side_effect=AssertionError('REMOTE START BEFORE ADMISSION')):
            with self.assertRaises(SystemExit) as e:
                fleet.cmd_run(self.args)
            self.assertEqual(e.exception.code, 75)

    def test_hot_remote_queues_before_transfer(self):
        self.launch_rejected(self.p, {})

    def test_missing_thermal_queues_before_transfer(self):
        self.p.pop('max_temp_c')
        self.launch_rejected(self.p, {})

    def test_offline_queues(self):
        self.launch_rejected({'error': 'probe failed'}, {})

    def test_groot_has_no_host_lane(self):
        self.assertEqual(fleet.eligible(fleet.registry()[1]['groot'], self.args, {}), 'no host lane')

    def test_explicit_paused_node_is_temporary_failure(self):
        self.n['lane_enabled'] = True
        with patch.object(fleet, 'registry', return_value=({}, {'mbp': self.n})), \
             patch.object(fleet, 'eligible', return_value='paused by fleet health'):
            with self.assertRaises(SystemExit) as e:
                fleet.cmd_run(self.args)
            self.assertEqual(e.exception.code, 75)

    def test_healthy_remote_reaches_dispatch(self):
        self.p['max_temp_c'] = 80
        with tempfile.TemporaryDirectory() as td, \
             patch.object(fleet, 'registry', return_value=({}, {'mbp': self.n})), \
             patch.object(fleet, 'k8s_nodes', return_value=self.kn), \
             patch.object(fleet, 'probe', return_value=self.p), \
             patch.object(fleet, 'STATE', pathlib.Path(td)), \
             patch.object(fleet.subprocess, 'run', side_effect=RuntimeError('DISPATCH_MBP_ONLY')):
            with self.assertRaisesRegex(RuntimeError, 'DISPATCH_MBP_ONLY'):
                fleet.cmd_run(self.args)

    def test_core_cli_browser_compositor_audio_preserved(self):
        cg = f'0::/user.slice/user-{os.getuid()}.slice/user@{os.getuid()}.service/app.slice/interactive.scope'
        data = {1:(0,'Hyprland',cg), 2:(1,'agent-control',cg), 3:(2,'zsh',cg),
                4:(3,'ffmpeg',cg), 5:(2,'chrome',cg), 6:(5,'renderer',cg),
                7:(2,'pipewire',cg), 8:(2,'agent-control',cg), 9:(8,'python3',cg),
                10:(1,'codex',cg)}
        self.assertEqual(classifier.select(data), [3,4,9])

    def test_genuine_gpu_batch_gets_envelope(self):
        cg = f'0::/user.slice/user-{os.getuid()}.slice/user@{os.getuid()}.service/app.slice/render.scope'
        self.assertEqual(classifier.select({1:(0,'agent-batch',cg),2:(1,'gpu-worker',cg)}),[1,2])

    def test_offline_tailnet_self_does_not_crash_health(self):
        with patch.object(fleet.subprocess,'run',return_value=types.SimpleNamespace(stdout='{"Self":{"TailscaleIPs":[]},"Peer":{}}')):
            self.assertEqual(fleet.tailnet_online(),{})

if __name__ == '__main__':
    unittest.main()
