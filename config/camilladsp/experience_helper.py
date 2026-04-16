#!/usr/bin/env python3
"""Shared helper for CamillaDSP audio experiences.

Reads the current base config, applies modifications, writes a temp config,
and reloads CamillaDSP via websocket.
"""

import copy
import os
import sys
import yaml
from camilladsp import CamillaClient

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_DIR = os.path.join(SCRIPT_DIR, "configs")
STATE_FILE = os.path.join(SCRIPT_DIR, ".state")
EXPERIENCE_CONFIG = os.path.join(CONFIG_DIR, "_experience-active.yml")

CDSP_ADDR = os.environ.get("CDSP_ADDR", "127.0.0.1")
CDSP_PORT = int(os.environ.get("CDSP_PORT", "1234"))


def load_state():
    """Load current profile and rate from state file."""
    profile = "clean"
    rate = "96000"
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            for line in f:
                line = line.strip()
                if line.startswith("CURRENT_PROFILE="):
                    profile = line.split("=", 1)[1].strip('"')
                elif line.startswith("CURRENT_RATE="):
                    rate = line.split("=", 1)[1].strip('"')
    return profile, rate


def base_config_path(profile, rate):
    """Get the base config file path for the given profile and rate."""
    if profile == "clean":
        return os.path.join(CONFIG_DIR, f"camilladsp-{rate}.yml")
    else:
        return os.path.join(CONFIG_DIR, f"camilladsp-{profile}-{rate}.yml")


def load_base_config():
    """Load the current base config as a dict."""
    profile, rate = load_state()
    path = base_config_path(profile, rate)
    with open(path) as f:
        return yaml.safe_load(f), profile, rate


def load_clean_config():
    """Load the clean base config (no spatial processing).

    Use this for experiences that provide their own spatial stage
    (e.g. concert-hall-teleporter, haas-widener) so they don't
    layer on top of crossfeed or BRIR.
    """
    _, rate = load_state()
    path = base_config_path("clean", rate)
    with open(path) as f:
        return yaml.safe_load(f), rate


def apply_config(config, label="experience"):
    """Write config to temp file and reload CamillaDSP."""
    with open(EXPERIENCE_CONFIG, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)

    try:
        client = CamillaClient(CDSP_ADDR, CDSP_PORT)
        client.connect()
        client.config.set_file_path(EXPERIENCE_CONFIG)
        client.general.reload()
        print(f"  Loaded: {label}")
    except Exception as e:
        print(f"  ERROR: websocket unavailable ({e})", file=sys.stderr)
        sys.exit(1)


def restore_base():
    """Restore the original base config (turn off experience)."""
    profile, rate = load_state()
    path = base_config_path(profile, rate)
    try:
        client = CamillaClient(CDSP_ADDR, CDSP_PORT)
        client.connect()
        client.config.set_file_path(path)
        client.general.reload()
        print(f"  Restored: {profile} @ {rate}Hz")
    except Exception as e:
        print(f"  ERROR: websocket unavailable ({e})", file=sys.stderr)
        sys.exit(1)


def add_filter_to_pipeline(config, filter_name, channels, position="before_limiter"):
    """Add a filter step to the pipeline before the limiter."""
    pipeline = config["pipeline"]
    if position == "before_limiter":
        # Find the first limiter step
        for i, step in enumerate(pipeline):
            if step.get("type") == "Filter" and "limiter" in step.get("names", []):
                pipeline.insert(i, {"type": "Filter", "channels": channels, "names": [filter_name]})
                return
    # Fallback: append before last step
    pipeline.insert(-1, {"type": "Filter", "channels": channels, "names": [filter_name]})


def add_stereo_filter_before_limiter(config, filter_name_l, filter_name_r=None):
    """Add a stereo filter pair before the limiter."""
    if filter_name_r is None:
        filter_name_r = filter_name_l
    pipeline = config["pipeline"]
    for i, step in enumerate(pipeline):
        if step.get("type") == "Filter" and "limiter" in step.get("names", []):
            pipeline.insert(i, {"type": "Filter", "channels": [1], "names": [filter_name_r]})
            pipeline.insert(i, {"type": "Filter", "channels": [0], "names": [filter_name_l]})
            return
