"""Every Windows script must be pure ASCII.

Windows PowerShell 5.1 reads a .ps1 without a BOM in the ANSI code page, so
the UTF-8 bytes of an em dash (E2 80 94) arrive as three characters, the last
being a right double quote that ends the string early: start-windows.ps1 then
fails to parse at all. cmd.exe has the same trouble with .bat files. Keeping
the scripts ASCII avoids both, whatever the code page.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Windows PowerShell's own parser reads the file the way `powershell -File`
# does (ANSI unless there is a BOM), so it catches what the ASCII check is for.
# The path travels in an environment variable, never on the command line:
# everything after -Command is joined into the one command, so a path placed
# there is a bare command and the script RUNS (the installer did, once).
PARSE = (
    "$e = $null; $t = $null; "
    "[void][System.Management.Automation.Language.Parser]::ParseFile($env:AIPROXY_PARSE_FILE, [ref]$t, [ref]$e); "
    "foreach ($x in $e) { 'line ' + $x.Extent.StartLineNumber + ': ' + $x.Message }"
)


def windows_scripts() -> list[Path]:
    found = [p for pattern in ("*.ps1", "*.bat", "*.cmd") for p in ROOT.glob(pattern)]
    found += [p for pattern in ("*.ps1", "*.bat", "*.cmd") for p in (ROOT / "windows").glob(pattern)]
    return sorted(found)


def test_windows_scripts_are_ascii():
    scripts = windows_scripts()
    assert any(p.name == "start-windows.ps1" for p in scripts), scripts
    bad = []
    for path in scripts:
        for lineno, line in enumerate(path.read_bytes().splitlines(), 1):
            if any(b > 0x7F for b in line):
                bad.append(f"{path.relative_to(ROOT)}:{lineno}")
    assert not bad, "non-ASCII bytes in: " + ", ".join(bad)


def test_windows_powershell_parses_every_script() -> bool:
    """Returns False (skipped) where Windows PowerShell 5.1 is not installed."""
    exe = shutil.which("powershell.exe") or shutil.which("powershell")
    if not exe:
        return False
    failures = []
    for path in windows_scripts():
        if path.suffix != ".ps1":
            continue
        # A closed stdin and no console window: with an inherited pipe for
        # stdin powershell.exe waits on it forever, and without a console of
        # its own it opens a visible window.
        out = subprocess.run(
            [exe, "-NoProfile", "-NonInteractive", "-Command", PARSE],
            env={**os.environ, "AIPROXY_PARSE_FILE": str(path)},
            stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if out.returncode != 0 or out.stdout.strip():
            failures.append(f"{path.relative_to(ROOT)}: {out.stdout.strip() or out.stderr.strip()}")
    assert not failures, "\n".join(failures)
    return True


if __name__ == "__main__":
    test_windows_scripts_are_ascii()
    if not test_windows_powershell_parses_every_script():
        print("(no powershell.exe: parse check skipped)")
    print("ok")
