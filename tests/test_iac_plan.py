import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "iac" / "plan.py"

spec = importlib.util.spec_from_file_location("iac_plan", MODULE_PATH)
plan = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(plan)


def test_resolve_host_uses_stable_logical_id():
    fleet = {
        "hosts": {
            "desktop": {"match_hostnames": ["0", "groot"]},
            "mbp": {"match_hostnames": ["mbp"]},
        }
    }
    host_id, _ = plan.resolve_host(fleet, "0")
    assert host_id == "desktop"


def test_plan_reports_missing_without_scheduling_removals():
    fleet = {
        "hosts": {
            "desktop": {
                "match_hostnames": ["0"],
                "package_groups": ["core"],
                "system_services": ["docker.service"],
                "user_services": [],
            }
        }
    }
    packages = {
        "core": {"packages": ["git", "docker"]},
        "overrides": {},
    }
    observed = {
        "host": {"hostname": "0"},
        "observations": {
            "pacman_explicit": {"data": ["git", "extra-package"]},
            "pacman_foreign": {"data": []},
            "system_services_enabled": {"data": ["NetworkManager.service enabled enabled"]},
            "user_services_enabled": {"data": []},
        },
    }

    result = plan.build_plan(fleet, packages, observed)

    assert result["status"] == "DRIFT"
    assert result["packages"]["missing"] == ["docker"]
    assert result["packages"]["observed_unmanaged_count"] == 1
    assert result["system_services"]["missing_enabled"] == ["docker.service"]


def test_arch_override_resolves_package_name():
    packages = {
        "apps": {"packages": ["cursor-bin"]},
        "overrides": {
            "cursor-bin": {
                "arch": {"name": "cursor-bin", "source": "aur"},
                "ubuntu": "cursor",
            }
        },
    }
    assert plan.desired_packages(packages, ["apps"]) == {"cursor-bin"}
