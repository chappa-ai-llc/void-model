#!/usr/bin/env bash
# Check the pinned stack on the real target (DGX Spark: CPython 3.12, Linux aarch64, CUDA).
# Installs requirements-lock-linux-aarch64-cp312.txt into a fresh venv (hash-checked, wheels only, no
# dependency resolution), runs `pip check`, the test suite, and a CUDA smoke test. Prints PASS or FAIL.
# Usage: bash tools/target_check.sh [WORK_DIR]   (from a clone of the repository)
set -euo pipefail
repo="$(cd "$(dirname "$0")/.." && pwd)"
work="${1:-$(mktemp -d -t void-target-XXXXXX)}"
py="${PYTHON:-python3.12}"
echo "repo $repo at $(git -C "$repo" rev-parse --short HEAD 2>/dev/null || echo unknown); work $work; $($py --version)"
echo "machine $(uname -m); $(nvidia-smi --query-gpu=name,driver_version --format=csv,noheader 2>/dev/null || echo 'no nvidia-smi')"
"$py" -m venv "$work/venv"
"$work/venv/bin/python" -m pip install --quiet --disable-pip-version-check --require-hashes --no-deps \
  --only-binary=:all: -r "$repo/requirements-lock-linux-aarch64-cp312.txt"
"$work/venv/bin/python" -m pip check
cd "$repo"
"$work/venv/bin/python" -m unittest discover -s tests -v
"$work/venv/bin/python" - <<'PY'
import sys, torch
sys.path.insert(0, ".")
print("torch", torch.__version__, "cuda", torch.version.cuda, "available", torch.cuda.is_available())
assert torch.cuda.is_available(), "CUDA is not available"
print("device", torch.cuda.get_device_name(0))
from videox_fun.models import CogVideoXTransformer3DModel, AutoencoderKLCogVideoX
dev, dt = "cuda", torch.bfloat16
m = CogVideoXTransformer3DModel(num_attention_heads=2, attention_head_dim=8, in_channels=4, out_channels=4,
    time_embed_dim=16, text_embed_dim=16, num_layers=1, sample_width=8, sample_height=8, sample_frames=5,
    max_text_seq_length=4, use_rotary_positional_embeddings=True).to(dev, dt).eval()
with torch.no_grad():
    out = m(torch.randn(1, 2, 4, 8, 8, device=dev, dtype=dt), torch.randn(1, 4, 16, device=dev, dtype=dt),
            torch.tensor([10], device=dev), return_dict=False)[0]
assert out.shape == (1, 2, 4, 8, 8) and torch.isfinite(out).all()
vae = AutoencoderKLCogVideoX(block_out_channels=(8, 8, 8, 8), latent_channels=4, norm_num_groups=4,
    layers_per_block=1).to(dev, dt).eval()
with torch.no_grad():
    dec = vae.decode(vae.encode(torch.randn(1, 3, 5, 16, 16, device=dev, dtype=dt)).latent_dist.sample()).sample
assert dec.shape[1] == 3 and torch.isfinite(dec).all()
print("CUDA smoke: transformer (rotary) and VAE forward OK on", torch.cuda.get_device_name(0))
PY
echo PASS
