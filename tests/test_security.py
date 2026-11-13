"""Security regression tests (standard library only; NumPy cases skip without it).

Run from the repository root:

    python -m unittest discover -s tests -v

They pin down the hardening described in docs/SECURITY.md: safe loading of
pickles and checkpoints, no remote code, no exec of spliced paths, and every
dependency pinned with ==.
"""

import importlib.util
import io
import json
import os
import pickle
import re
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UTILS = ROOT / "videox_fun" / "utils"


def _load_utils_module(name):
    """Import videox_fun/utils/<name>.py without importing torch or the model code."""
    pkg_name = "_vf_utils_under_test"
    if pkg_name not in sys.modules:
        pkg = types.ModuleType(pkg_name)
        pkg.__path__ = [str(UTILS)]
        sys.modules[pkg_name] = pkg
    full = f"{pkg_name}.{name}"
    if full in sys.modules:
        return sys.modules[full]
    spec = importlib.util.spec_from_file_location(full, UTILS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[full] = module
    spec.loader.exec_module(module)
    return module


safe_pickle = _load_utils_module("safe_pickle")
sampler_state = _load_utils_module("sampler_state")
timeout = _load_utils_module("timeout")


class _Evil:
    """Pickles to a call of os.system: what a hostile .pkl file would do."""

    def __reduce__(self):
        return (os.system, ("echo pwned",))


def _python_files():
    for path in ROOT.rglob("*.py"):
        rel = path.relative_to(ROOT)
        if rel.parts[0] in {"scratchpad", ".git", "tests"}:
            continue
        yield rel, path.read_text(encoding="utf-8", errors="replace")


class SafePickleTests(unittest.TestCase):
    def test_refuses_code_execution(self):
        payload = pickle.dumps(_Evil())
        with self.assertRaises(pickle.UnpicklingError):
            safe_pickle.safe_loads(payload)

    def test_refuses_arbitrary_class(self):
        payload = pickle.dumps(_Evil, protocol=4)  # a class reference by name
        with self.assertRaises(pickle.UnpicklingError):
            safe_pickle.safe_loads(payload)

    def test_loads_plain_data(self):
        data = {"armature": [[0.1, 0.2], [0.3]], "objects": {"cup": (1, 2.5)}, "ok": True}
        self.assertEqual(safe_pickle.safe_load(io.BytesIO(pickle.dumps(data))), data)

    def test_loads_numpy_arrays(self):
        try:
            import numpy as np
        except ImportError:
            self.skipTest("numpy not installed")
        data = {"vertices": np.arange(12, dtype=np.float32).reshape(4, 3),
                "faces": np.array([[0, 1, 2]], dtype=np.int64),
                "scalar": np.float64(1.5)}
        for protocol in (2, 4, 5):
            loaded = safe_pickle.safe_loads(pickle.dumps(data, protocol=protocol))
            self.assertTrue(np.array_equal(loaded["vertices"], data["vertices"]))
            self.assertEqual(loaded["faces"].dtype, np.int64)
            self.assertEqual(loaded["scalar"], 1.5)

    def test_blender_copy_matches(self):
        a = (UTILS / "safe_pickle.py").read_text()
        b = (ROOT / "data_generation" / "safe_pickle.py").read_text()
        self.assertEqual(a, b, "data_generation/safe_pickle.py must stay identical to videox_fun/utils/safe_pickle.py")


class SamplerStateTests(unittest.TestCase):
    def test_json_state(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "sampler_pos_start.json").write_text(json.dumps([120, 3]))
            self.assertEqual(sampler_state.load_sampler_state(d), (120, 3))

    def test_legacy_pickle_state(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "sampler_pos_start.pkl").write_bytes(pickle.dumps([7, 1]))
            self.assertEqual(sampler_state.load_sampler_state(d), (7, 1))

    def test_hostile_legacy_pickle_refused(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "sampler_pos_start.pkl").write_bytes(pickle.dumps(_Evil()))
            with self.assertRaises(pickle.UnpicklingError):
                sampler_state.load_sampler_state(d)

    def test_missing_state(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(sampler_state.load_sampler_state(d))


class FuncTimeoutTests(unittest.TestCase):
    def test_returns_value(self):
        self.assertEqual(timeout.func_timeout(5, lambda a, b=0: a + b, args=(2,), kwargs={"b": 3}), 5)

    def test_passes_errors_through(self):
        def boom():
            raise KeyError("x")
        with self.assertRaises(KeyError):
            timeout.func_timeout(5, boom)

    def test_times_out(self):
        def slow():
            for _ in range(200):
                time.sleep(0.05)
        start = time.monotonic()
        with self.assertRaises(timeout.FunctionTimedOut):
            timeout.func_timeout(0.2, slow)
        self.assertLess(time.monotonic() - start, 2)


class StaticSecurityTests(unittest.TestCase):
    def test_torch_load_is_weights_only(self):
        bad = []
        for rel, text in _python_files():
            for m in re.finditer(r"torch\.load\(([^()]*(?:\([^()]*\)[^()]*)*)\)", text):
                if "weights_only=True" not in m.group(1):
                    bad.append(f"{rel}: {m.group(0)}")
        self.assertEqual(bad, [], "torch.load must pass weights_only=True")

    def test_no_plain_pickle_load(self):
        bad = [f"{rel}" for rel, text in _python_files()
               if re.search(r"\bpickle\.loads?\(", text) and rel.name != "safe_pickle.py"]
        self.assertEqual(bad, [], "use safe_pickle.safe_load, never pickle.load")

    def test_no_trust_remote_code(self):
        bad = [f"{rel}" for rel, text in _python_files() if re.search(r"trust_remote_code\s*=\s*True", text)]
        self.assertEqual(bad, [], "trust_remote_code=True runs code from the model repo")

    def test_no_exec_of_files(self):
        bad = [f"{rel}" for rel, text in _python_files() if re.search(r"exec\(open\(", text)]
        self.assertEqual(bad, [])

    def test_no_shell_true(self):
        bad = [f"{rel}" for rel, text in _python_files() if re.search(r"shell\s*=\s*True", text)]
        self.assertEqual(bad, [])

    def test_requirements_pinned(self):
        files = [ROOT / "requirements.txt"] + sorted((ROOT / "data_generation").glob("requirements*.txt"))
        bad = []
        for f in files:
            for line in f.read_text().splitlines():
                line = line.split("#", 1)[0].strip() if not line.lstrip().startswith("decord @") else line.strip()
                if not line:
                    continue
                if line.startswith("decord @ "):
                    if "#sha256=" not in line:
                        bad.append(f"{f.name}: {line} (direct URL without #sha256=)")
                    continue
                spec = line.split(";", 1)[0].strip()
                if not re.fullmatch(r"[A-Za-z0-9_.\-\[\]]+==[A-Za-z0-9_.+\-]+", spec):
                    bad.append(f"{f.name}: {line}")
        self.assertEqual(bad, [], "pin every requirement with == (hash-pin direct URLs)")

    def test_no_unauthenticated_web_api(self):
        self.assertFalse((ROOT / "videox_fun" / "api").exists(),
                         "the unauthenticated FastAPI endpoints were removed; see docs/SECURITY.md")
        self.assertFalse((ROOT / "videox_fun" / "ui").exists())


if __name__ == "__main__":
    unittest.main()
