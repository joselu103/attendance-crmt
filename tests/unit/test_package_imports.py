import os
import subprocess
import sys


def test_importing_audit_module_has_no_runtime_side_effects(tmp_path) -> None:
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("ATTENDANCE_")
    }

    result = subprocess.run(
        [sys.executable, "-c", "import attendance_crmt.audit"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert list(tmp_path.rglob("*.sqlite3")) == []
