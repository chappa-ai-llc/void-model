"""Smoke tests for the model code against the pinned libraries (torch, diffusers, transformers).

They build tiny models on the CPU, so no checkpoint or GPU is needed. Run them after every
dependency upgrade, in an environment installed from requirements.txt:

    python -m unittest tests.test_smoke_models -v

Skipped when torch is not installed (tests/test_security.py stays standard-library only).
"""

import importlib
import os
import pkgutil
import py_compile
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Modules that were already unimportable before the 2026-11-13 upgrade and that nothing imports:
# the Wan pipeline expects an AutoencoderKLWan model this repository does not contain.
KNOWN_UNIMPORTABLE = {"videox_fun.pipeline.pipeline_wan_fun"}

try:
    import torch
except ImportError:  # pragma: no cover - depends on the environment
    torch = None


@unittest.skipIf(torch is None, "torch not installed")
class SmokeTests(unittest.TestCase):
    def test_every_file_compiles(self):
        bad = []
        with tempfile.TemporaryDirectory() as out:
            for i, path in enumerate(ROOT.rglob("*.py")):
                if path.relative_to(ROOT).parts[0] in {"scratchpad", ".git"}:
                    continue
                try:
                    py_compile.compile(str(path), doraise=True, cfile=os.path.join(out, f"{i}.pyc"))
                except py_compile.PyCompileError as exc:
                    bad.append(str(exc))
        self.assertEqual(bad, [])

    def test_every_videox_fun_module_imports(self):
        import videox_fun
        failed = {}
        for info in pkgutil.walk_packages(videox_fun.__path__, "videox_fun."):
            if info.name in KNOWN_UNIMPORTABLE:
                continue
            try:
                importlib.import_module(info.name)
            except Exception as exc:  # report every failure at once
                failed[info.name] = f"{type(exc).__name__}: {exc}"
        self.assertEqual(failed, {})

    def test_tiny_transformer_forward_and_reload(self):
        from videox_fun.models import CogVideoXTransformer3DModel
        torch.manual_seed(0)
        model = CogVideoXTransformer3DModel(
            num_attention_heads=2, attention_head_dim=8, in_channels=4, out_channels=4,
            time_embed_dim=16, text_embed_dim=16, num_layers=1, sample_width=8, sample_height=8,
            sample_frames=5, max_text_seq_length=4, norm_eps=1e-5,
        ).eval()
        hidden = torch.randn(1, 2, 4, 8, 8)
        text = torch.randn(1, 4, 16)
        with torch.no_grad():
            out = model(hidden, text, torch.tensor([10]), return_dict=False)[0]
        self.assertEqual(tuple(out.shape), (1, 2, 4, 8, 8))

        with tempfile.TemporaryDirectory() as d:
            model.save_pretrained(d)
            loaded = CogVideoXTransformer3DModel.from_pretrained(d, torch_dtype=torch.float32).eval()
            with torch.no_grad():
                again = loaded(hidden, text, torch.tensor([10]), return_dict=False)[0]
            self.assertTrue(torch.allclose(out, again, atol=1e-5))

            # The .bin path goes through torch.load(weights_only=True).
            for name in os.listdir(d):
                if name.endswith(".safetensors"):
                    os.remove(os.path.join(d, name))
            torch.save(model.state_dict(), os.path.join(d, "diffusion_pytorch_model.bin"))
            loaded_bin = CogVideoXTransformer3DModel.from_pretrained(d, torch_dtype=torch.float32).eval()
            with torch.no_grad():
                again_bin = loaded_bin(hidden, text, torch.tensor([10]), return_dict=False)[0]
            self.assertTrue(torch.allclose(out, again_bin, atol=1e-5))

    def test_weights_only_refuses_code(self):
        class Evil:
            def __reduce__(self):
                return (os.system, ("echo pwned",))

        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "evil.bin")
            torch.save({"x": Evil()}, path)
            with self.assertRaises(Exception):
                torch.load(path, map_location="cpu", weights_only=True)

    def test_tiny_vae_roundtrip(self):
        from videox_fun.models import AutoencoderKLCogVideoX
        torch.manual_seed(0)
        vae = AutoencoderKLCogVideoX(
            block_out_channels=(8, 8, 8, 8), latent_channels=4, norm_num_groups=4, layers_per_block=1,
        ).eval()
        video = torch.randn(1, 3, 5, 16, 16)
        with torch.no_grad():
            latents = vae.encode(video).latent_dist.sample()
            decoded = vae.decode(latents).sample
        self.assertEqual(latents.shape[1], 4)
        self.assertEqual(decoded.shape[1], 3)

    def test_text_encoder_and_schedulers(self):
        from diffusers import CogVideoXDDIMScheduler, DDIMScheduler
        from transformers import T5Config
        from videox_fun.models import T5EncoderModel
        cfg = T5Config(vocab_size=32, d_model=16, d_kv=8, d_ff=32, num_layers=1, num_heads=2)
        enc = T5EncoderModel(cfg).eval()
        with torch.no_grad():
            out = enc(torch.tensor([[1, 2, 3, 0]])).last_hidden_state
        self.assertEqual(tuple(out.shape), (1, 4, 16))
        for cls in (DDIMScheduler, CogVideoXDDIMScheduler):
            sched = cls()
            sched.set_timesteps(4)
            self.assertEqual(len(sched.timesteps), 4)


if __name__ == "__main__":
    unittest.main()
