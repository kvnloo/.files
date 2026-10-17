#!/usr/bin/env python3
"""Opt-in Oura Gen 3 BLE gestures -> local argv actions. No cloud or audio capture."""
from __future__ import annotations

import argparse
import asyncio
from collections import deque
from dataclasses import dataclass
import json
import math
from pathlib import Path
import stat
import subprocess
import sys
import time
import tomllib
from typing import Callable

SERVICE = "98ed0001-a541-11e4-b6a0-0002a5d5c51b"
WRITE = "98ed0002-a541-11e4-b6a0-0002a5d5c51b"
NOTIFY = "98ed0003-a541-11e4-b6a0-0002a5d5c51b"
DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "config/oura-gestures/actions.toml"


def accel_samples(frame: bytes) -> list[tuple[int, int, int]]:
    """Decode 0x33 ACM notification (one or two signed LE xyz samples)."""
    if not frame or frame[0] != 0x33 or len(frame) not in (10, 16):
        return []
    return [tuple(int.from_bytes(frame[i + j:i + j + 2], "little", signed=True)
                  for j in (0, 2, 4)) for i in (4, 10) if i + 6 <= len(frame)]


def realtime_start(seconds: int) -> bytes:
    if not 1 <= seconds <= 3600:
        raise ValueError("seconds must be 1..3600 (bounded, not always-on)")
    minutes = (seconds + 59) // 60
    return b"\x06\x07\x20\x00\x00\x00" + minutes.to_bytes(2, "little") + b"\x00"


REALTIME_OFF = bytes.fromhex("060400000000")


def nonce_cipher(key: bytes, nonce: bytes) -> bytes:
    """AES-128 ECB of the 15-byte nonce + PKCS#7 pad, for Oura app auth only."""
    if len(key) != 16 or len(nonce) != 15:
        raise ValueError("expected 16-byte key and 15-byte nonce")
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    encryptor = Cipher(algorithms.AES(key), modes.ECB()).encryptor()
    return encryptor.update(nonce + b"\x01") + encryptor.finalize()


def read_key(path: Path) -> bytes:
    path = path.expanduser()
    if path.stat().st_mode & (stat.S_IRWXG | stat.S_IRWXO):
        raise ValueError("key file permissions must be private (chmod 600)")
    key = bytes.fromhex(path.read_text(encoding="ascii").strip())
    if len(key) != 16:
        raise ValueError("auth key must be exactly 16 bytes (32 hex characters)")
    return key


@dataclass(frozen=True)
class GestureConfig:
    tap_threshold: float = 450.0
    tap_gap: float = 0.38
    min_gap: float = 0.09
    max_pulse: float = 0.12
    cooldown: float = 0.65
    shake_threshold: float = 1100.0


class GestureDetector:
    """Orientation-independent impulse clustering; feed ~50 Hz raw xyz."""

    def __init__(self, config: GestureConfig = GestureConfig()):
        self.cfg = config
        self.previous: tuple[int, int, int] | None = None
        self.last_time = -math.inf
        self.pulse_at: float | None = None
        self.pulse_overlong = False
        self.armed = True
        self.taps: list[float] = []
        self.shake_edges: deque[float] = deque()
        self.cooldown_until = -math.inf

    def _finish_taps(self, now: float) -> list[str]:
        if not self.taps or now - self.taps[-1] <= self.cfg.tap_gap:
            return []
        count = len(self.taps)
        self.taps.clear()
        if count in (2, 3, 4):
            self.cooldown_until = now + self.cfg.cooldown
            return [{2: "double_tap", 3: "triple_tap", 4: "quadruple_tap"}[count]]
        return []

    def tick(self, now: float) -> list[str]:
        """Allow last tap to settle even when no new BLE packet arrives."""
        return self._finish_taps(now)

    def feed(self, now: float, xyz: tuple[int, int, int]) -> list[str]:
        if now < self.last_time:
            raise ValueError("samples must be ordered by monotonic time")
        events = self._finish_taps(now)
        if self.previous is None or now - self.last_time > 0.3:
            self.previous, self.last_time = xyz, now
            self.pulse_at = None
            self.armed = True
            self.shake_edges.clear()
            return events
        jerk = math.dist(xyz, self.previous)
        self.previous, self.last_time = xyz, now
        if now < self.cooldown_until:
            self.pulse_at = None
            return events

        # A shake is a run of large excursions, not just two quick impacts.
        if jerk >= self.cfg.shake_threshold:
            if not self.shake_edges or now - self.shake_edges[-1] >= 0.055:
                self.shake_edges.append(now)
        while self.shake_edges and now - self.shake_edges[0] > 0.9:
            self.shake_edges.popleft()
        if len(self.shake_edges) >= 5:
            self.shake_edges.clear()
            self.taps.clear()
            self.pulse_at = None
            self.armed = False
            self.cooldown_until = now + self.cfg.cooldown
            return events + ["shake"]

        if self.pulse_at is not None:
            if now - self.pulse_at > self.cfg.max_pulse:
                self.pulse_overlong = True
            if jerk < self.cfg.tap_threshold * 0.38:
                if not self.pulse_overlong:
                    t = self.pulse_at
                    if self.taps and t - self.taps[-1] < self.cfg.min_gap:
                        pass  # bounce, no extra tap
                    elif self.taps and t - self.taps[-1] > self.cfg.tap_gap:
                        self.taps = [t]
                    elif len(self.taps) < 4:
                        self.taps.append(t)
                    else:
                        self.taps = [t]
                self.pulse_at = None
                self.armed = True
        elif self.armed and jerk >= self.cfg.tap_threshold:
            self.pulse_at = now
            self.pulse_overlong = False
            self.armed = False
        return events


def load_actions(path: Path) -> dict[str, list[str]]:
    with path.expanduser().open("rb") as handle:
        raw = tomllib.load(handle)
    actions = raw.get("actions", {})
    known = {"double_tap", "triple_tap", "quadruple_tap", "shake"}
    if not isinstance(actions, dict) or any(k not in known for k in actions):
        raise ValueError("actions must be a map of known gestures")
    for name, argv in actions.items():
        if (not isinstance(argv, list) or not argv
                or any(not isinstance(arg, str) or not arg.strip() for arg in argv)):
            raise ValueError(f"{name}: action must be a nonempty argv array (no shell)")
    return actions


class ActionRouter:
    def __init__(self, actions: dict[str, list[str]], dry_run: bool = False,
                 runner: Callable = subprocess.run):
        self.actions, self.dry_run, self.runner = actions, dry_run, runner

    def dispatch(self, gesture: str) -> None:
        argv = self.actions.get(gesture)
        if not argv:
            print(f"{gesture}: unbound", flush=True)
            return
        if self.dry_run:
            print(f"{gesture}: DRY RUN {json.dumps(argv)}", flush=True)
            return
        try:
            result = self.runner(argv, capture_output=True, text=True, timeout=6, check=False)
            if result.returncode:
                print(f"{gesture}: command failed ({result.returncode}): "
                      f"{(result.stderr or result.stdout).strip()[:240]}", file=sys.stderr)
            else:
                # Tern ctl returns JSON {ok:false} with exit 0 in some versions.
                if len(argv) >= 2 and argv[:2] == ["tern", "ctl"]:
                    try:
                        reply = json.loads(result.stdout)
                    except (ValueError, TypeError):
                        print(f"{gesture}: unexpected Tern response", file=sys.stderr)
                        return
                    if not reply.get("ok", False):
                        print(f"{gesture}: Tern rejected action: "
                              f"{str(reply.get('error', 'unknown'))[:240]}", file=sys.stderr)
                        return
                print(f"{gesture}: triggered", flush=True)
        except (OSError, subprocess.TimeoutExpired) as error:
            print(f"{gesture}: action unavailable: {error}", file=sys.stderr)


async def scan() -> None:
    try:
        from bleak import BleakScanner
    except ImportError as error:
        raise RuntimeError("install bleak: python -m pip install bleak") from error
    entries = await BleakScanner.discover(timeout=8.0, return_adv=True)
    found = [(device, adv) for device, adv in entries.values()
             if "oura" in (device.name or adv.local_name or "").lower()
             or SERVICE in (s.lower() for s in adv.service_uuids)]
    if not found:
        print("No advertising Oura ring; try disconnecting its phone connection.")
    for device, adv in found:
        print(f"{device.address}  {device.name or adv.local_name or '(unnamed)'}  RSSI={adv.rssi}")


async def next_ext(responses: asyncio.Queue[bytes], ext_tag: int) -> bytes:
    async with asyncio.timeout(8):
        while True:
            packet = await responses.get()
            if len(packet) >= 3 and packet[:1] == b"\x2f" and packet[2] == ext_tag:
                return packet[3:]


async def listen(address: str, key: bytes, seconds: int, detector: GestureDetector,
                 router: ActionRouter) -> None:
    try:
        from bleak import BleakClient
    except ImportError as error:
        raise RuntimeError("install bleak: python -m pip install bleak") from error
    responses: asyncio.Queue[bytes] = asyncio.Queue(maxsize=64)
    samples: asyncio.Queue[tuple[float, tuple[int, int, int]]] = asyncio.Queue(maxsize=512)
    async with BleakClient(address, timeout=12) as client:
        def on_notify(_characteristic, data: bytearray) -> None:
            frame = bytes(data)
            if frame[:1] == b"\x33":
                points = accel_samples(frame)
                hz = frame[2] if len(frame) > 2 and 10 <= frame[2] <= 250 else 50
                stamp = time.monotonic()
                for idx, xyz in enumerate(points):
                    try:
                        samples.put_nowait((stamp - (len(points) - idx - 1) / hz, xyz))
                    except asyncio.QueueFull:
                        # Deliberately drop stale samples, not queue unbounded latency.
                        try:
                            samples.get_nowait()
                            samples.put_nowait((stamp, xyz))
                        except asyncio.QueueEmpty:
                            pass
            else:
                try:
                    responses.put_nowait(frame)
                except asyncio.QueueFull:
                    pass

        await client.start_notify(NOTIFY, on_notify)
        started = False
        try:
            await client.write_gatt_char(WRITE, bytes.fromhex("2f012b"), response=True)
            nonce = await next_ext(responses, 0x2c)
            cipher = nonce_cipher(key, nonce)
            await client.write_gatt_char(WRITE, b"\x2f\x11\x2d" + cipher, response=True)
            status = await next_ext(responses, 0x2e)
            if status != b"\x00":
                raise RuntimeError("Oura BLE authentication rejected; existing key may differ")
            await client.write_gatt_char(WRITE, realtime_start(seconds), response=True)
            started = True
            print(f"Authenticated. Streaming ~50 Hz for up to {seconds}s. Ctrl-C to stop.")
            end = time.monotonic() + seconds
            while time.monotonic() < end:
                try:
                    stamp, xyz = await asyncio.wait_for(samples.get(), timeout=0.05)
                    for gesture in detector.feed(stamp, xyz):
                        router.dispatch(gesture)
                except asyncio.TimeoutError:
                    pass
                for gesture in detector.tick(time.monotonic()):
                    router.dispatch(gesture)
        finally:
            if started:
                try:
                    await asyncio.shield(client.write_gatt_char(WRITE, REALTIME_OFF, response=True))
                except Exception as error:
                    print(f"BLE stream OFF write failed: {error}; ring also has time limit", file=sys.stderr)
            await client.stop_notify(NOTIFY)


def replay(path: Path, detector: GestureDetector, router: ActionRouter) -> None:
    """JSONL: {'t': seconds, 'x': counts, 'y': counts, 'z': counts}; no BLE needed."""
    with path.open(encoding="utf8") as handle:
        last = 0.0
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            last = float(record["t"])
            for gesture in detector.feed(last, (int(record["x"]), int(record["y"]), int(record["z"]))):
                router.dispatch(gesture)
        for gesture in detector.tick(last + detector.cfg.tap_gap + 0.01):
            router.dispatch(gesture)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("scan", "listen", "replay"))
    parser.add_argument("replay_file", nargs="?", type=Path)
    parser.add_argument("--address", help="ring BLE MAC/address (from scan)")
    parser.add_argument("--key-file", type=Path, help="private 16-byte ring app-auth key (hex)")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--seconds", type=int, default=120)
    parser.add_argument("--tap-threshold", type=float, default=450.0)
    parser.add_argument("--dry-run", action="store_true", help="detect but don't execute actions")
    args = parser.parse_args(argv)
    try:
        if args.mode == "scan":
            asyncio.run(scan())
            return 0
        if args.tap_threshold <= 0 or not math.isfinite(args.tap_threshold):
            parser.error("--tap-threshold must be a finite positive number")
        detector = GestureDetector(GestureConfig(tap_threshold=args.tap_threshold))
        router = ActionRouter(load_actions(args.config), dry_run=args.dry_run or args.mode == "replay")
        if args.mode == "replay":
            if not args.replay_file:
                parser.error("replay needs a JSONL file")
            replay(args.replay_file, detector, router)
        elif args.mode == "listen":
            if not args.address or not args.key_file:
                parser.error("listen needs --address and --key-file; never factory-resets or pairs")
            realtime_start(args.seconds)
            asyncio.run(listen(args.address, read_key(args.key_file), args.seconds, detector, router))
        return 0
    except (OSError, ValueError, RuntimeError, TimeoutError) as error:
        print(f"oura-gestures: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
