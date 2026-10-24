"""Tiny admission-only regressions: never start a real build or network transfer."""
import importlib.machinery
import pathlib
import os
import sys
import time
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
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

class PhonePlacement(unittest.TestCase):
    def test_s25_gates_before_transfer_and_never_falls_back_to_groot(self):
        nodes = fleet.registry()[1]
        nodes = {name: nodes[name] for name in ("omarchy-phone", "groot")}
        args = types.SimpleNamespace(
            node=None, cls="phone", arch="arm64", tolerate=["phone"],
            cmd=["true"], mem=None, cpus=None, timeout=60, src=str(ROOT),
            no_src=False, keep=False, fetch=[], input=[], guest=False)
        p = {"ts": time.time(), "transport": "adb", "mem_available_mb": 0,
             "load1": 0, "ncpu": 8, "services": {},
             "power": {"on_ac": False, "source": "adb", "battery_temp_c": 99,
                       "android_thermal_status": 6,
                       "batteries": [{"pct": 1, "status": "Discharging"}]}}
        with tempfile.TemporaryDirectory() as td, \
             patch.object(fleet, "registry", return_value=({}, nodes)), \
             patch.object(fleet, "k8s_nodes", return_value={}), \
             patch.object(fleet, "probe", return_value=p), \
             patch.object(fleet, "STATE", pathlib.Path(td)), \
             patch.object(fleet.subprocess, "run", side_effect=RuntimeError("TRANSFER")) as transfer:
            with self.assertRaises(SystemExit) as refused:
                fleet.cmd_run(args)
            self.assertEqual(refused.exception.code, 75)
            transfer.assert_not_called()
            # Critical uncharged battery holds before the native helper can
            # transfer anything. Charging permits the same 1% phone.
            p["power"]["on_ac"] = True
            with self.assertRaisesRegex(RuntimeError, "TRANSFER"):
                fleet.cmd_run(args)
            argv = transfer.call_args.args[0]
            self.assertEqual(argv[:4], [sys.executable, str(ROOT/"scripts/fleet-adb"),
                                       "run", "omarchy-phone"])
            self.assertEqual(argv[-2:], ["--", "true"])
            self.assertNotIn("100.113.138.100", " ".join(argv))
            self.assertFalse(any("ssh" in value for value in argv))
            # At 2% unplugged the native lane remains usable even with hot,
            # memory-starved guest telemetry: Android owns those resources.
            p["power"]["on_ac"] = False
            p["power"]["batteries"][0]["pct"] = 2
            with self.assertRaisesRegex(RuntimeError, "TRANSFER"):
                fleet.cmd_run(args)
            p["power"]["batteries"][0]["pct"] = 1
            transfer.reset_mock()
            with self.assertRaises(SystemExit) as hot:
                fleet.cmd_run(args)
            self.assertEqual(hot.exception.code, 75)
            transfer.assert_not_called()


if __name__ == '__main__':
    unittest.main()
