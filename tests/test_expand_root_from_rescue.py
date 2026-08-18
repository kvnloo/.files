#!/usr/bin/env python3
"""Safety tests use JSON fixtures only; they never open a block device."""
import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import rescue_expand_fstab as fstab_contract
import rescue_expand_receipt as receipt_contract

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/expand-root-from-rescue.sh"
MOCK_APPLY = ROOT / "scripts/rescue_expand_mock_apply.py"
CONFIRM = "EXPAND 23446Z P1 4196352-281020415 DELETE P2 KEEP P3 281020416"


PARTUUIDS = {
    1: "5fed8d1d-f6a6-44d3-9608-0408425a9383",
    2: "c3c2176b-e843-4490-958c-c73eb542a22d",
    3: "ffbd4444-5995-4ed1-abd1-c0ac108848ef",
    4: "11878bd8-0fee-471e-90b7-3c18db40fa85",
}


def part(n, start, size, fstype, uuid, mounts=None):
    return {
        "name": f"nvme0n1p{n}", "path": f"/dev/nvme0n1p{n}",
        "type": "part", "size": size * 512, "start": start,
        "fstype": fstype, "uuid": uuid, "partuuid": PARTUUIDS.get(n, f"fixture-p{n}"),
        "mountpoints": mounts or [], "model": None, "serial": None,
        "log-sec": 512, "phy-sec": 512,
    }


def original():
    return {"blockdevices": [{
        "name": "nvme0n1", "path": "/dev/nvme0n1", "type": "disk",
        "size": 500107862016, "start": None, "fstype": None, "uuid": None,
        "partuuid": None, "mountpoints": [], "model": "Samsung SSD 960 EVO 500GB",
        "serial": "S3EUNB0J523446Z", "log-sec": 512, "phy-sec": 512,
        "children": [
            part(1, 4196352, 209715200, "xfs", "9e575c2d-52cc-41ec-8b3f-15afd8191c81"),
            part(2, 213911552, 67108864, "swap", "316f4699-5371-4798-9873-68f2b6194cb4"),
            part(3, 281020416, 695752719, "xfs", "f70404dd-c13b-4070-8d7c-d6d5e91db153"),
            part(4, 2048, 4194304, "vfat", "DBCE-C10E"),
        ],
    }]}


def make_sparse_table(image):
    with image.open("wb") as stream:
        stream.truncate(500107862016)
    layout = """label: gpt
unit: sectors
first-lba: 34

start=4196352, size=209715200, type=linux, uuid=5fed8d1d-f6a6-44d3-9608-0408425a9383
start=213911552, size=67108864, type=swap, uuid=c3c2176b-e843-4490-958c-c73eb542a22d
start=281020416, size=695752719, type=linux, uuid=ffbd4444-5995-4ed1-abd1-c0ac108848ef
start=2048, size=4194304, type=uefi, uuid=11878bd8-0fee-471e-90b7-3c18db40fa85
"""
    subprocess.run(["sfdisk", "--wipe", "never", str(image)], input=layout,
                   text=True, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


class RescueExpansionSafety(unittest.TestCase):
    def run_fixture(self, data, *args):
        with tempfile.TemporaryDirectory() as td:
            fixture = Path(td) / "fixture.json"
            fixture.write_text(json.dumps(data), encoding="utf-8")
            env = os.environ | {
                "RESCUE_EXPAND_TEST_MODE": "1",
                "RESCUE_EXPAND_FIXTURE": str(fixture),
            }
            return subprocess.run(
                [str(SCRIPT), *args, "--output-dir", td], env=env,
                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                timeout=10, check=False,
            )

    def assert_refused(self, data, needle):
        r = self.run_fixture(data, "--plan")
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn(needle, r.stdout)

    def test_exact_original_plan(self):
        r = self.run_fixture(original(), "--plan")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("no device commands executed", r.stdout)

    def test_wrong_disk_serial(self):
        d = original(); d["blockdevices"][0]["serial"] = "WRONG"
        self.assert_refused(d, "serial drift")

    def test_wrong_sector_size(self):
        d = original(); d["blockdevices"][0]["log-sec"] = 4096
        self.assert_refused(d, "sector size drift")

    def test_wrong_swap_uuid(self):
        d = original(); d["blockdevices"][0]["children"][1]["uuid"] = "wrong"
        self.assert_refused(d, "p2 UUID drift")

    def test_wrong_order_or_gap(self):
        d = original(); d["blockdevices"][0]["children"][1]["start"] += 1
        self.assert_refused(d, "p2 geometry drift")

    def test_mounted_target(self):
        d = original(); d["blockdevices"][0]["children"][2]["mountpoints"] = ["/workspace"]
        self.assert_refused(d, "p3 is mounted/in use")

    def test_luks_ambiguity(self):
        d = original(); d["blockdevices"][0]["children"][0]["fstype"] = "crypto_LUKS"
        self.assert_refused(d, "p1 filesystem drift")

    def test_extra_partition(self):
        d = original(); d["blockdevices"][0]["children"].append(part(5, 900000000, 10, None, None))
        self.assert_refused(d, "partition set drift")

    def test_idempotent_already_grown(self):
        d = original(); children = d["blockdevices"][0]["children"]
        children[0]["size"] = 276824064 * 512
        d["blockdevices"][0]["children"] = [children[0], children[2], children[3]]
        r = self.run_fixture(d, "--verify-only")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("already expanded", r.stdout)

    def test_already_grown_identity_drift_fails(self):
        for key, value, needle in [
            ("partuuid", "wrong", "partition set drift"),
            ("type", "disk", "partition set drift"),
            ("path", "/dev/alias", "path identity drift"),
            ("mountpoints", ["/boot"], "mounted/in use"),
        ]:
            with self.subTest(key=key):
                d = original(); children = d["blockdevices"][0]["children"]
                children[0]["size"] = 276824064 * 512
                d["blockdevices"][0]["children"] = [children[0], children[2], children[3]]
                d["blockdevices"][0]["children"][0 if key != "mountpoints" else 2][key] = value
                self.assert_refused(d, needle)

    def test_no_apply_even_with_confirmation_in_tests(self):
        r = self.run_fixture(original(), "--apply", "--confirm",
            "EXPAND 23446Z P1 4196352-281020415 DELETE P2 KEEP P3 281020416")
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn("apply is disabled in test mode", r.stdout)

    def test_fstab_exact_parser_and_byte_preservation(self):
        uuid = fstab_contract.SWAP_SOURCE
        raw = (
            b"# UUID=316f4699-5371-4798-9873-68f2b6194cb4 none swap defaults 0 0\n"
            b"  # disabled line\n"
            + f"UUID={uuid.removeprefix('UUID=')}prefix none swap defaults 0 0\n".encode()
            + b"/dev/zram0 none swap defaults 0 0\n"
            + b"/mnt/zer0models/.swap/emergency.swap none swap defaults 0 0\n"
            + f"\t{uuid}\tnone\tswap\tdefaults\t0 0 # exact\n".encode()
            + b"UUID=other none swap defaults 0 0\n"
        )
        final = fstab_contract.transform(raw)
        self.assertNotIn(f"\t{uuid}\t".encode(), final)
        self.assertIn(b"/dev/zram0", final)
        self.assertIn(b"emergency.swap", final)
        self.assertIn(b"prefix", final)
        fstab_contract.check_final(raw, final)

    def test_fstab_duplicate_or_wrong_type_fails(self):
        line = f"{fstab_contract.SWAP_SOURCE} none swap defaults 0 0\n".encode()
        for raw in [line + line, line.replace(b" swap ", b" xfs "), line.replace(b" none ", b"/swap ")]:
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    fstab_contract.transform(raw)

    def test_receipt_topology_rejects_target_alias_p4_and_mapper(self):
        rows = [
            {"path": "/dev/nvme0n1", "type": "disk", "pkname": None, "maj:min": "259:0"},
            {"path": "/dev/nvme0n1p4", "type": "part", "pkname": "/dev/nvme0n1", "maj:min": "259:4"},
            {"path": "/dev/dm-0", "type": "crypt", "pkname": None, "maj:min": "253:0"},
            {"path": "/dev/sdb", "type": "disk", "pkname": None, "maj:min": "8:16"},
            {"path": "/dev/sdb1", "type": "part", "pkname": "/dev/sdb", "maj:min": "8:17"},
        ]
        self.assertEqual(receipt_contract.physical_roots(rows, "259:4", {}), {"259:0"})
        self.assertEqual(receipt_contract.physical_roots(rows, "253:0", {"253:0": ["259:4"]}), {"259:0"})
        self.assertEqual(receipt_contract.physical_roots(rows, "8:17", {}), {"8:16"})
        self.assertIn("overlay", receipt_contract.DENIED_FS)

    @unittest.skipUnless(shutil.which("sfdisk"), "sfdisk unavailable")
    def test_sparse_regular_file_partition_sequence_keeps_p3(self):
        """Exercise real sfdisk syntax on a sparse regular file, never a block device."""
        with tempfile.TemporaryDirectory() as td:
            image = Path(td) / "disk.img"
            make_sparse_table(image)
            before = json.loads(subprocess.check_output(
                ["sfdisk", "--json", str(image)], text=True))
            subprocess.run(
                ["sfdisk", "--delete", str(image), "2"], check=True,
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            )
            resize = (
                "start=4196352, size=276824064, type=linux, "
                "uuid=5fed8d1d-f6a6-44d3-9608-0408425a9383\n"
            )
            subprocess.run(
                ["sfdisk", "--no-reread", "--force", "-N", "1", str(image)],
                input=resize, text=True, check=True, stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            after = json.loads(subprocess.check_output(
                ["sfdisk", "--json", str(image)], text=True))
            b = before["partitiontable"]["partitions"][2]
            a = after["partitiontable"]["partitions"][1]
            self.assertEqual((a["start"], a["size"], a["uuid"]),
                             (b["start"], b["size"], b["uuid"]))
            p1 = after["partitiontable"]["partitions"][0]
            self.assertEqual((p1["start"], p1["size"]), (4196352, 276824064))

    @unittest.skipUnless(shutil.which("sfdisk"), "sfdisk unavailable")
    def test_executable_mock_failure_boundaries_and_idempotence(self):
        pre_grow = {"before-delete", "after-delete", "after-resize", "before-grow"}
        points = pre_grow | {"during-grow", "after-grow", "fstab-install", "final-verification"}
        for point in sorted(points):
            with self.subTest(point=point), tempfile.TemporaryDirectory() as td:
                root = Path(td); image = root / "disk.img"; make_sparse_table(image)
                fstab = root / "fstab"
                fstab.write_bytes(
                    f"{fstab_contract.SWAP_SOURCE} none swap defaults 0 0\n".encode()
                    + b"/dev/zram0 none swap defaults 0 0\n"
                    + b"/mnt/zer0models/.swap/emergency.swap none swap defaults 0 0\n"
                )
                receipt = root / "receipt"
                result = subprocess.run(
                    [sys.executable, str(MOCK_APPLY), "--image", str(image), "--fstab", str(fstab),
                     "--receipt", str(receipt), "--confirm", CONFIRM, "--failpoint", point],
                    text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
                )
                self.assertNotEqual(result.returncode, 0, result.stdout)
                commands = json.loads((receipt / "commands.json").read_text())
                current = json.loads(subprocess.check_output(["sfdisk", "--json", str(image)], text=True))
                partitions = current["partitiontable"]["partitions"]
                if point in pre_grow:
                    if point == "before-delete":
                        self.assertNotIn("rollback-partition-table", commands)
                    else:
                        self.assertIn("rollback-partition-table", commands)
                    self.assertEqual(len(partitions), 4)
                    self.assertEqual((partitions[2]["start"], partitions[3]["start"]), (281020416, 2048))
                else:
                    self.assertIn("NO_ROLLBACK_AFTER_GROW_STARTED", commands)
                    self.assertEqual(len(partitions), 3)
                    self.assertEqual((partitions[1]["start"], partitions[2]["start"]), (281020416, 2048))

        with tempfile.TemporaryDirectory() as td:
            root = Path(td); image = root / "disk.img"; make_sparse_table(image)
            fstab = root / "fstab"
            fstab.write_text(f"{fstab_contract.SWAP_SOURCE} none swap defaults 0 0\n/dev/zram0 none swap defaults 0 0\n")
            receipt = root / "success"
            command = [sys.executable, str(MOCK_APPLY), "--image", str(image), "--fstab", str(fstab),
                       "--receipt", str(receipt), "--confirm", CONFIRM]
            self.assertEqual(subprocess.run(command, check=False).returncode, 0)
            self.assertEqual((receipt / "checkpoint").read_text(), "verified\n")
            second = root / "second"
            command[command.index(str(receipt))] = str(second)
            self.assertEqual(subprocess.run(command, check=False).returncode, 0)
            self.assertEqual(json.loads((second / "commands.json").read_text()), ["already-grown"])

    @unittest.skipUnless(shutil.which("sfdisk"), "sfdisk unavailable")
    def test_mock_confirmation_refuses_before_writes(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); image = root / "disk.img"; make_sparse_table(image)
            before = subprocess.check_output(["sfdisk", "--dump", str(image)])
            fstab = root / "fstab"; fstab.write_text(f"{fstab_contract.SWAP_SOURCE} none swap defaults 0 0\n")
            result = subprocess.run([sys.executable, str(MOCK_APPLY), "--image", str(image),
                "--fstab", str(fstab), "--receipt", str(root / "receipt"), "--confirm", "wrong"])
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(before, subprocess.check_output(["sfdisk", "--dump", str(image)]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
