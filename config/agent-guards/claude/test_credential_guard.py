"""All commands here are inert strings sent to the hook, never to a shell."""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest


HOOK = Path(__file__).with_name("credential-guard.py")
CUSTODY_CASES = json.loads((HOOK.parent.parent / "custody-cases.json").read_text())
DENIED = [
    "pass-cli", "pass-cli --help", "/usr/bin/pass-cli item list", "./pass-cli --version",
    "~/.local/bin/pass-cli", "$HOME/.local/bin/pass-cli", "${HOME}/.local/bin/pass-cli",
    r"p\ass-cli", "'pass-cli'", '"pass"-cli', "pa''ss-cli", "pass-\\\ncli",
    "bash -c 'pass-cli'", "sh -c 'pass-cli'", "zsh -lc 'pass-cli'", "fish -c 'pass-cli'",
    "bash -c \"sh -c 'pass-cli'\"", "eval 'pass-cli'", "exec pass-cli",
    "env pass-cli", "env -i pass-cli", "env -u TOKEN X=Y pass-cli", "env -S 'pass-cli'",
    "sudo -u passd /usr/bin/pass-cli", "sudo -n -- pass-cli", "doas pass-cli",
    "nohup pass-cli", "timeout 2 pass-cli", "timeout -s KILL 2 pass-cli", "xargs pass-cli",
    "xargs -I {} pass-cli {}", "command -- pass-cli", "builtin pass-cli",
    "echo $(pass-cli)", "echo `pass-cli`", "echo $(echo $(pass-cli))",
    "true; pass-cli", "true && pass-cli", "false || pass-cli", "echo hi | pass-cli",
    "true\npass-cli", "(pass-cli)", "sh <<< 'pass-cli'", "sh <<EOF\npass-cli\nEOF",
    "echo cGFzcy1jbGk= | base64 -d | sh", "base64 --decode docs/payload | bash",
    "X=pass-cli; $X", "export X=pass-cli; $X", "X=/usr/bin/pass-cli; ${X}",
    "exec -a friendly pass-cli", "sudo -n pass-cli", "doas -n pass-cli", "xargs -P 2 pass-cli",
    "env -S sh -c pass-cli", "env --split-string='sh -c pass-cli' harmless",
    "env --chdir=$HOME/.gnupg cat key", "env -C ~/.gnupg cat key",
    '''python3 -c 'import subprocess; subprocess.run(["env"])' ''',
    "if true; then pass-cli; fi", "while pass-cli; do true; done", "{ pass-cli; }",
    '''python -c 'import subprocess; subprocess.run(["pass-cli"])' ''',
    '''python3 -c 'import os; os.popen("pass-cli")' ''',
    '''node -e 'require("child_process").spawn("pass-cli")' ''',
    '''perl -e 'system("pass-cli")' ''', '''ruby -e 'exec("pass-cli")' ''',
    '''deno eval 'Deno.Command("pass-cli").spawn()' ''',
    '''bun -e 'Bun.spawn(["pass-cli"])' ''',
    '''python3 -c 'print(open("~/.gnupg/private-keys-v1.d/key").read())' ''',
    '''node -e 'require("fs").readFileSync("/var/lib/passd/db")' ''',
    "python3 -c 'import os; print(os.environ)'", "node -e 'console.log(process.env)'",
    "ruby -e 'puts ENV'", "python3 -m keyring get service account",
    "python3 -c 'import keyring; keyring.get_password(\"s\", \"u\")'",
    "env", "env | sort", "env -i", "printenv", "printenv TOKEN", "set", "set | cat",
    "declare -x", "declare -p", "export -p", "export", "cat /proc/self/environ",
    "cat /proc/123/environ", "cat < /proc/*/environ", "echo hi > ~/.local/share/passd/db",
    "cat ~/.local/share/proton-pass/data", "less ~/.config/proton-pass-cli/session",
    "head ~/.cache/proton-pass/x", "tail ~/.local/share/keyrings/login.keyring",
    "cp ~/.gnupg/private-keys-v1.d/key dest", "tar cf out ~/.password-store",
    "rsync ~/.local/share/passd/ out/", "grep x /var/lib/passd/db",
    "find ~/.local/share/proton-pass", "sqlite3 ~/.local/share/passd/db .dump",
    "strings ~/.config/proton-pass/data", "xxd ~/.gnupg/secring.gpg",
    "cd ~/.local/share/passd && cat db", "cat $HOME/.gnupg/../.gnupg/key",
    "cat -- /var/lib/passd/db", "dd if=/var/lib/passd/db", "man pass-cli",
] + [f"{tool} --help" for tool in "proton-pass secret-tool gnome-keyring-daemon gnome-keyring seahorse kwallet-query kwalletcli lssecret keyring bws bw op gopass pass".split()]
ALLOWED = [
    'git commit -m "mention pass-cli in docs"', "grep -r pass-cli docs/", "rg printenv",
    "echo $PATH", "echo pass-cli", "printf '%s' pass-cli", "git status", "pwd",
    "cat README.md", "python3 -c 'print(42)'", "node -e 'console.log(42)'",
    "env FOO=bar git status", "env -i PATH=/usr/bin git status", "env -u TOKEN git status",
    "bash -c 'echo hello'", "true && git status", "git diff | head -10",
    "set -eu", "export PATH=/usr/bin", "grep -r secret-tool config/",
    "cat config/passd/README.md", "ls config/proton-pass", "python3 -m unittest",
    "echo bypassed", "compass --help", "git commit -m 'use subprocess with pass-cli in docs'",
]


def run_hook(data, raw=False):
    result = subprocess.run([sys.executable, str(HOOK)], input=data if raw else json.dumps(data),
                            text=True, capture_output=True, check=False)
    if result.returncode != 0 or result.stderr:
        raise AssertionError("Hook failed without a protocol decision")
    if not result.stdout:
        return None
    output = json.loads(result.stdout)["hookSpecificOutput"]
    assert output["hookEventName"] == "PreToolUse"
    assert output["permissionDecision"] == "deny"
    return output["permissionDecisionReason"]


class GuardTests(unittest.TestCase):
    def test_custody_cases(self):
        for tool, args, denied in CUSTODY_CASES:
            with self.subTest(tool=tool, args=args):
                self.assertEqual(run_hook({"tool_name": tool, "tool_input": args}) is not None, denied)

    def test_protected_file_tools(self):
        for tool in ("Read", "Grep", "Glob", "Edit", "Write", "NotebookEdit"):
            for key in ("file_path", "path", "pattern", "notebook_path"):
                with self.subTest(tool=tool, key=key):
                    self.assertIsNotNone(run_hook({"tool_name": tool, "tool_input": {key: "~/.gnupg/../.gnupg/key"}}))

    def test_symlink_and_relative_paths(self):
        # Tracked fixture symlink points into a fake HOME; no actual store is accessed.
        home = HOOK.parent / "fixtures" / "home"
        env = dict(os.environ, HOME=str(home))
        for path in ("../home/.gnupg/key", "key-alias/key"):
            result = subprocess.run([sys.executable, str(HOOK)], env=env, text=True,
                input=json.dumps({"tool_name": "Read", "cwd": str(home.parent / "work"), "tool_input": {"path": path}}),
                capture_output=True, check=True)
            self.assertEqual(json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"], "deny")
        result = subprocess.run([sys.executable, str(HOOK)], env=env, text=True,
            input=json.dumps({"tool_name": "Bash", "cwd": str(home.parent / "work"), "tool_input": {
                "command": "python3 -c 'print(open(\"key-alias/key\").read())'"}}),
            capture_output=True, check=True)
        self.assertEqual(json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_source_edit_mentions_allowed(self):
        self.assertIsNone(run_hook({"tool_name": "Edit", "tool_input": {
            "file_path": "config/passd/README.md", "new_string": "pass-cli ~/.gnupg/key os.environ"}}))

    def test_mcp_nested_args(self):
        for value in ("/usr/bin/pass-cli --help", "cat ~/.gnupg/key", "os.environ"):
            self.assertIsNotNone(run_hook({"tool_name": "mcp__server__exec", "tool_input": {"nested": [{"command": value}]}}))
        self.assertIsNone(run_hook({"tool_name": "mcp__server__get", "tool_input": {"path": "docs/guide.md"}}))

    def test_malformed(self):
        for raw, denied in [('{"tool_name":"Bash","tool_input":pass-cli', True),
                            ('{"tool_name":"Bash","tool_input":git', False),
                            ('{"tool_name":"Read", pass-cli', False), ('[]', False)]:
            self.assertEqual(run_hook(raw, raw=True) is not None, denied)
        for args in ({"command": ["pass-cli"]}, {"incorrect": "pass-cli"}):
            self.assertIsNotNone(run_hook({"tool_name": "Bash", "tool_input": args}))

    def test_static_settings_protocol(self):
        settings = json.loads(HOOK.with_name("settings.deny.json").read_text())
        rules = settings["permissions"]["deny"]
        for rule in ("Bash(pass:*)", "Bash(pass *)", "Bash(*/pass-cli *)", "Read(//proc/*/environ)", "Edit(//var/lib/passd/**)"):
            self.assertIn(rule, rules)
        for rule in ("Bash(pass-cli-run)", "Bash(pass-cli-run:*)", "Bash(*/pass-cli-run *)",
                     "Bash(/usr/local/lib/proton-pass/pass-cli-run *)", "Bash(sudo *passvault*)",
                     "Bash(su *passd*)", "Bash(systemd-run *passvault*)"):
            self.assertIn(rule, rules)
        for path in ("//var/lib/passvault", "//var/lib/passd", "//usr/local/lib/proton-pass"):
            for tool in ("Read", "Edit", "Grep", "Glob"):
                for suffix in ("", "/**"):
                    self.assertIn(f"{tool}({path}{suffix})", rules)
        entry = settings["hooks"]["PreToolUse"][0]
        self.assertEqual(entry["matcher"], "Bash|Read|Grep|Glob|Edit|Write|NotebookEdit|mcp__.*")
        self.assertEqual(entry["hooks"][0]["type"], "command")

    def test_reason_does_not_echo_input(self):
        reason = run_hook({"tool_name": "Bash", "tool_input": {"command": "pass-cli CANARY_NEVER_ECHO"}})
        self.assertNotIn("CANARY", reason)


def command_test(command, denied):
    def test(self):
        self.assertEqual(run_hook({"tool_name": "Bash", "tool_input": {"command": command}}) is not None, denied)
    return test


for label, commands, denied in (("denied", DENIED, True), ("allowed", ALLOWED, False)):
    for number, command in enumerate(commands):
        setattr(GuardTests, f"test_{label}_{number:03d}", command_test(command, denied))


if __name__ == "__main__":
    unittest.main()
