"""Synthetic/offline contract tests; never require a ring, BLE or Tern."""
import asyncio
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import types

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("oura_gestures", ROOT / "scripts/oura-gestures.py")
oura = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = oura
SPEC.loader.exec_module(oura)


def classify(taps=(), *, spikes=(), step=0.02, total=2.0):
    detector = oura.GestureDetector()
    events = []
    signals = set(round(t / step) for t in taps)
    heavy = set(round(t / step) for t in spikes)
    for i in range(int(total / step)):
        t = round(i * step, 6)
        x = 1500 if i in heavy else (720 if i in signals else 0)
        events.extend(detector.feed(t, (x, 0, 1000)))
    events.extend(detector.tick(total + 1))
    return events


@pytest.mark.parametrize("taps,event", [
    ([0.4, 0.63], "double_tap"),
    ([0.4, 0.61, 0.82], "triple_tap"),
    ([0.4, 0.58, 0.76, 0.94], "quadruple_tap"),
])
def test_tap_clusters(taps, event):
    assert classify(taps) == [event]


def test_single_tap_and_noise_do_not_trigger():
    assert classify([0.5]) == []
    assert classify([]) == []
    assert classify([0.5, 1.0]) == []


def test_bounce_rejected():
    assert classify([0.4, 0.46, 0.63]) == ["double_tap"]


def test_shake_separate_from_taps():
    assert classify(spikes=[0.30, 0.43, 0.56, 0.69, 0.82]) == ["shake"]


def test_slow_sustained_motion_not_a_tap():
    d = oura.GestureDetector()
    out = []
    for i in range(100):
        out += d.feed(i * 0.02, (i * 30, 0, 1000))
    assert out == []


def test_parser_signed_axes_and_bad_frame():
    frame = bytes.fromhex("330c3201feff0200fdff040005000600")
    assert oura.accel_samples(frame) == [(-2, 2, -3), (4, 5, 6)]
    assert oura.accel_samples(b"\x33\x00") == []
    assert oura.accel_samples(b"\x44" + frame[1:]) == []


def test_stream_packet_bounded_and_off():
    assert oura.realtime_start(1).hex() == "060720000000010000"
    assert oura.realtime_start(61).hex() == "060720000000020000"
    assert oura.REALTIME_OFF.hex() == "060400000000"
    with pytest.raises(ValueError):
        oura.realtime_start(0)
    with pytest.raises(ValueError):
        oura.realtime_start(3601)


def test_auth_matches_recorded_reference():
    key = bytes.fromhex("4431967d8bacc2659743142b68391d9a")
    nonce = bytes.fromhex("0e2d6a0a08c99b4365f458e6e97382")
    assert oura.nonce_cipher(key, nonce).hex() == "a38a8772d3acb6db5c2b516dd56987c8"


def test_key_file_permissions(tmp_path):
    key = tmp_path / "key.hex"
    key.write_text("aa" * 16)
    key.chmod(0o600)
    assert oura.read_key(key) == bytes.fromhex("aa" * 16)
    key.chmod(0o644)
    with pytest.raises(ValueError, match="private"):
        oura.read_key(key)


def test_no_shell_and_tern_ok_check(capsys):
    commands = []

    def runner(argv, **kwargs):
        commands.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0, '{"ok":true}', "")

    a = oura.ActionRouter({"double_tap": ["tern", "ctl", "carly", "open"]}, runner=runner)
    a.dispatch("double_tap")
    assert commands[0][0] == ["tern", "ctl", "carly", "open"]
    assert "shell" not in commands[0][1]
    assert "triggered" in capsys.readouterr().out


def test_tern_rejection_is_not_a_success(capsys):
    def runner(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 0, '{"ok":false,"error":"no socket"}', "")
    oura.ActionRouter({"double_tap": ["tern", "ctl", "carly", "open"]}, runner=runner).dispatch("double_tap")
    read = capsys.readouterr()
    assert "rejected" in read.err
    assert "triggered" not in read.out


def test_actions_loaded_and_replay_never_executes(tmp_path, capsys):
    cfg = ROOT / "config/oura-gestures/actions.toml"
    assert oura.load_actions(cfg)["double_tap"] == ["tern", "ctl", "carly", "open"]
    trace = tmp_path / "double.jsonl"
    lines = []
    for i in range(90):
        t = round(i * 0.02, 4)
        lines.append(json.dumps({"t": t, "x": 720 if i in (20, 31) else 0, "y": 0, "z": 1000}))
    trace.write_text("\n".join(lines) + "\n")
    assert oura.main(["replay", str(trace), "--config", str(cfg)]) == 0
    assert 'double_tap: DRY RUN ["tern", "ctl", "carly", "open"]' in capsys.readouterr().out


def test_missing_auth_fails_before_ble(capsys):
    with pytest.raises(SystemExit):
        oura.main(["listen", "--address", "AA:BB"])
    assert "--key-file" in capsys.readouterr().err


def test_full_ble_handshake_and_teardown(monkeypatch):
    # Mock exact recorded nonce/auth exchange; loop is intentionally only 1s.
    writes = []

    class FakeClient:
        def __init__(self, address, timeout):
            assert address == "AA:BB"

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            pass

        async def start_notify(self, uuid, cb):
            assert uuid == oura.NOTIFY
            self.cb = cb

        async def stop_notify(self, uuid):
            assert uuid == oura.NOTIFY

        async def write_gatt_char(self, uuid, data, response):
            assert uuid == oura.WRITE and response
            data = bytes(data)
            writes.append(data)
            if data == bytes.fromhex("2f012b"):
                self.cb(None, bytearray.fromhex("2f102c0e2d6a0a08c99b4365f458e6e97382"))
            if data[:3] == bytes.fromhex("2f112d"):
                self.cb(None, bytearray.fromhex("2f022e00"))

    monkeypatch.setitem(sys.modules, "bleak", types.SimpleNamespace(BleakClient=FakeClient))
    detector = oura.GestureDetector()
    router = oura.ActionRouter({}, dry_run=True)
    key = bytes.fromhex("4431967d8bacc2659743142b68391d9a")
    asyncio.run(oura.listen("AA:BB", key, 1, detector, router))
    assert writes == [
        bytes.fromhex("2f012b"),
        bytes.fromhex("2f112da38a8772d3acb6db5c2b516dd56987c8"),
        bytes.fromhex("060720000000010000"),
        oura.REALTIME_OFF,
    ]


def test_capture_private_outside_repository(tmp_path):
    target = tmp_path / "oura.jsonl"
    with oura.open_capture(target) as handle:
        handle.write('{"t": 0, "x": 0, "y": 0, "z": 1000}\n')
    assert target.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        oura.open_capture(target)
    with pytest.raises(ValueError, match="outside"):
        oura.open_capture(ROOT / "secrets.jsonl")
