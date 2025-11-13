import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


TARGET_FILES = [
    ROOT / "scripts" / "workflow_utils" / "governance_reflex_learning_model.py",
    ROOT / "scripts" / "workflow_utils" / "governance_reflex_meta_evaluator.py",
    ROOT / "scripts" / "artifact_integrity_check.py",
]


TARGET_DIRS = [
    ROOT / "scripts" / "audit",
    ROOT / "scripts" / "ai",
    ROOT / "scripts" / "federation",
]


def read_text(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8")
    except Exception:
        return ""


def list_py_files(d: Path):
    for dirpath, _, filenames in os.walk(d):
        for fn in filenames:
            if fn.endswith(".py"):
                yield Path(dirpath) / fn


def test_no_utcnow_in_target_files():
    for p in TARGET_FILES:
        assert p.exists(), f"Missing expected file: {p}"
        content = read_text(p)
        assert "datetime.utcnow(" not in content, f"Found deprecated utcnow() in {p}"
        assert "datetime.datetime.utcnow(" not in content, f"Found deprecated utcnow() in {p}"


def test_no_utcnow_in_target_dirs():
    for d in TARGET_DIRS:
        if not d.exists():
            continue
        for p in list_py_files(d):
            content = read_text(p)
            assert "datetime.utcnow(" not in content, f"Found deprecated utcnow() in {p}"
            assert "datetime.datetime.utcnow(" not in content, f"Found deprecated utcnow() in {p}"
