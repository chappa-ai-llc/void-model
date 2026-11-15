"""Tests for the mask pipeline's VLM backend choice (issue #4). Standard library only.

Run from the repository root:

    python -m unittest discover -s tests -v

They pin down the offline default (a local server, no key, the local model name), the Gemini key read
from GEMINI_API_KEY_FILE, the old option names, and that stage 2 and run_pipeline.sh use all of it.
"""

import argparse
import ast
import importlib.util
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REASONER = ROOT / "VLM-MASK-REASONER"

_spec = importlib.util.spec_from_file_location("vlm_backend", REASONER / "vlm_backend.py")
vb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vb)


def _parse(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("--config")
    vb.add_arguments(parser)
    return parser.parse_args(argv)


class DefaultsAreOffline(unittest.TestCase):
    def test_default_is_local_vllm_with_gemma_and_no_key(self):
        s = vb.resolve_settings(environ={})
        self.assertEqual(s.backend, "vllm")
        self.assertEqual(s.base_url, "http://127.0.0.1:8000/v1")
        self.assertEqual(s.model, "google/gemma-4-31b-it")
        self.assertEqual(s.api_key, vb.LOCAL_PLACEHOLDER_KEY)
        self.assertFalse(s.sends_video)

    def test_local_backends_need_no_key_even_when_one_is_set(self):
        for backend, port in (("ollama", 11434), ("llama.cpp", 8080), ("vllm", 8000)):
            s = vb.resolve_settings(backend, environ={"GEMINI_API_KEY": "should-not-be-used"})
            self.assertEqual(s.base_url, f"http://127.0.0.1:{port}/v1")
            self.assertNotEqual(s.api_key, "should-not-be-used")

    def test_server_port_and_model_are_used(self):
        s = vb.resolve_settings("ollama", "10.1.2.3", 9999, "gemma4:31b", environ={})
        self.assertEqual(s.base_url, "http://10.1.2.3:9999/v1")
        self.assertEqual(s.model, "gemma4:31b")

    def test_ipv6_server_is_bracketed(self):
        self.assertEqual(vb.resolve_settings("vllm", "::1", environ={}).base_url, "http://[::1]:8000/v1")

    def test_server_must_be_a_bare_host(self):
        for bad in ("evil.example/x", "user@host", "host?x", "", "a b"):
            with self.assertRaises(ValueError):
                vb.resolve_settings("vllm", bad, environ={})

    def test_unknown_backend_refused(self):
        with self.assertRaises(ValueError):
            vb.resolve_settings("openai", environ={})


class GeminiKey(unittest.TestCase):
    def test_gemini_without_a_key_refuses(self):
        with self.assertRaises(RuntimeError) as cm:
            vb.resolve_settings("gemini", environ={})
        self.assertIn("GEMINI_API_KEY_FILE", str(cm.exception))

    def test_gemini_key_from_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "key")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("k-from-file\n")
            s = vb.resolve_settings("gemini", environ={"GEMINI_API_KEY_FILE": path, "GEMINI_API_KEY": "env"})
        self.assertEqual(s.api_key, "k-from-file")
        self.assertEqual(s.base_url, vb.GEMINI_BASE_URL)
        self.assertEqual(s.model, vb.DEFAULT_GEMINI_MODEL)
        self.assertTrue(s.sends_video)

    def test_empty_key_file_refused(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "key")
            open(path, "w").close()
            with self.assertRaises(RuntimeError):
                vb.resolve_settings("gemini", environ={"GEMINI_API_KEY_FILE": path})

    def test_old_environment_variable_still_works(self):
        s = vb.resolve_settings("gemini", environ={"GEMINI_API_KEY": "k-env"})
        self.assertEqual(s.api_key, "k-env")


class Options(unittest.TestCase):
    def test_defaults(self):
        a = _parse([])
        self.assertEqual((a.vlm_backend, a.vlm_server, a.vlm_port, a.vlm_model), ("vllm", "127.0.0.1", None, None))

    def test_old_option_names_still_parse(self):
        a = _parse(["--analysis-self-host-type", "ollama", "--analysis-self-host-server", "h",
                    "--analysis-self-host-port", "1", "--analysis-self-host-model", "m"])
        self.assertEqual((a.vlm_backend, a.vlm_server, a.vlm_port, a.vlm_model), ("ollama", "h", 1, "m"))
        self.assertEqual(_parse(["--model", "x"]).vlm_model, "x")


class Stage2UsesTheBackend(unittest.TestCase):
    source = (REASONER / "stage2_vlm_analysis.py").read_text(encoding="utf-8")

    def test_no_gemini_key_or_cloud_url_in_stage2(self):
        self.assertNotIn("GEMINI_API_KEY", self.source)
        self.assertNotIn("googleapis.com", self.source)
        self.assertNotIn("chappa_backend", self.source)

    def test_process_config_reads_the_config_argument(self):
        tree = ast.parse(self.source)
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "process_config")
        first = fn.body[1]  # after the docstring
        self.assertEqual(ast.unparse(first), "config_path = Path(args.config)")

    def test_cloud_gateway_variant_removed(self):
        self.assertFalse((REASONER / "stage2_vlm_analysis_cf.py").exists())


class PipelinePassesTheOptions(unittest.TestCase):
    def test_run_pipeline_forwards_vlm_options(self):
        text = (REASONER / "run_pipeline.sh").read_text(encoding="utf-8")
        self.assertRegex(text, r'stage2_vlm_analysis\.py" \\\n\s+--config "\$CONFIG" "\$\{VLM_ARGS\[@\]\}"')
        for opt in ("--vlm-backend", "--vlm-server", "--vlm-port", "--vlm-model"):
            self.assertIn(opt, text)

    def test_run_pipeline_parses(self):
        subprocess.run(["bash", "-n", str(REASONER / "run_pipeline.sh")], check=True)


class OpenAiIsPinned(unittest.TestCase):
    def test_openai_in_requirements_and_lock(self):
        req = (ROOT / "requirements.txt").read_text(encoding="utf-8")
        self.assertRegex(req, r"(?m)^openai==\d+\.\d+\.\d+")
        lock = (ROOT / "requirements-lock-linux-aarch64-cp312.txt").read_text(encoding="utf-8")
        for pkg in ("openai", "jiter", "sniffio"):
            self.assertRegex(lock, rf"(?m)^{pkg}==\S+ \\\n\s+--hash=sha256:[0-9a-f]{{64}}")


if __name__ == "__main__":
    unittest.main()
