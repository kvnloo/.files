"""llama-server units must leave GPU layers to --fit, never pin them (-ngl / --n-gpu-layers).

--fit only adjusts *unset* arguments, so a pinned `--n-gpu-layers 99` switches it off. When ComfyUI held
VRAM, sr-decision-llama OOMed at load and Restart=on-failure crash-looped it every 10 s (11-15/16).
Unpinned, the same load under 11 GB of contention offloads the rest to CPU and serves (2 s request)."""
import re
from pathlib import Path

UNITS = Path(__file__).resolve().parents[1] / "config/systemd/user"
PIN = re.compile(r"(?:^|\s)(?:-ngl|--n-gpu-layers|--gpu-layers)(?:=|\s)")


def exec_starts(text: str):
    joined = re.sub(r"\\\n", " ", text)
    return [l for l in joined.splitlines() if l.lstrip().startswith("ExecStart=") and "llama-server" in l]


def test_llama_server_units_leave_gpu_layers_to_fit():
    bad = [f"{p.relative_to(UNITS)}: {l.strip()[:140]}"
           for p in sorted(UNITS.rglob("*")) if p.is_file() and p.suffix in {".service", ".conf"}
           for l in exec_starts(p.read_text(errors="replace")) if PIN.search(l)]
    assert not bad, "\n".join(bad)


def test_pin_detector_sees_both_spellings():
    assert exec_starts("ExecStart=/x/llama-server \\\n  -m m --n-gpu-layers 99 \\\n  --parallel 4\n")
    assert PIN.search("ExecStart=/x/llama-server -m m -ngl 99")
    assert PIN.search("ExecStart=/x/llama-server --n-gpu-layers=99")
    assert not PIN.search("ExecStart=/x/llama-server -m m --fit on")
