"""Verify payload boundaries and real CLI behavior from a fresh ZIP extraction.

Only the packaged executable runs; no game is installed or changed.
"""
import argparse
import json
import os
import subprocess
import tempfile
import zipfile
from pathlib import Path, PurePosixPath


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    with zipfile.ZipFile(args.archive) as archive:
        names = archive.namelist()
        for name in names:
            path = PurePosixPath(name.replace("\\", "/"))
            assert not path.is_absolute() and ".." not in path.parts and ":" not in str(path), name
            assert path.suffix.lower() not in (".ps1", ".py", ".bat", ".dll", ".addon64", ".addon32"), name
        roots = {PurePosixPath(name).parts[0] for name in names}
        assert roots == {f"DLSS5-AIO-v{args.version}"}, roots
        with tempfile.TemporaryDirectory(prefix="AIO fresh extraction with spaces ") as directory:
            archive.extractall(directory)
            folder = Path(directory) / next(iter(roots))
            exe = folder / "DLSS5-AIO.exe"
            assert exe.stat().st_size > 1_000_000
            for name in ("README.txt", "CHANGELOG.md", "LICENSE", "licenses/Python-LICENSE.txt",
                         "licenses/Tcl-LICENSE.txt", "licenses/Tk-LICENSE.txt", "licenses/Autopilot-MIT.txt"):
                assert (folder / name).is_file(), name
            env = dict(os.environ, LOCALAPPDATA=str(Path(directory) / "isolated-profile"))
            for flag, code, expected in (("--version", 0, args.version), ("--self-test", 0, '"status": "ok"'),
                                          ("--unknown-option", 2, "unrecognized arguments")):
                result = subprocess.run([str(exe), flag], capture_output=True, text=True, env=env,
                                        cwd=folder, timeout=60)
                assert result.returncode == code, (flag, result.returncode, result.stdout, result.stderr)
                assert expected in result.stdout + result.stderr, (flag, result.stdout, result.stderr)
                if flag == "--self-test":
                    assert json.loads(result.stdout)["status"] == "ok"
    print("PASS: payload-only ZIP, licenses, fresh extraction, packaged version/self-test/invalid CLI")


if __name__ == "__main__":
    main()
