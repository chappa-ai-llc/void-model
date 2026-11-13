# Security — void-model

As of 2026-11-13 (main after the security sweep; see `git log`). This page is the reference for how the
repository keeps its dependencies and code safe, and what was changed in the 2026-11-13 sweep.

## What this project exposes

void-model is a research codebase: command-line inference and training scripts, a mask-reasoning
pipeline (`VLM-MASK-REASONER/`), Blender data-generation scripts (`data_generation/`) and a notebook.
It ships **no hosted web front end and no network service**. The main risks are the files it reads:
model checkpoints, pickled datasets and the Python packages it installs. The one interactive page,
`data_generation/physics_review_ui.py` (Streamlit), runs on this machine only (see below).

Because there is no hosted web front end, the chappa.ai Security Self-Check standard
(`chappa-ai-llc/security-self-check`), which audits a public front door, does not apply. Re-assess this
if a web UI or API is ever added.

## Dependencies

- Every requirement in `requirements.txt` and `data_generation/requirements.txt` is pinned with `==`.
  Every package comes from PyPI as a wheel, with no custom binary and no direct URL.
  `tests/test_security.py` fails on an unpinned line.
- Video decoding uses PyAV (`av`), which is maintained and has FFmpeg in its wheels. It replaced decord, which
  had no release since 2021 and needed a custom ARM64 build. `videox_fun/utils/video_reader.py` keeps decord's
  interface, and its frames match decord 0.6.0 exactly on the sample videos (`tests/test_smoke_models.py`).
- The Kubric generator runs in Kubric's own Docker image, pinned by digest (`data_generation/README.md`).
  It is no longer a PyPI install: the PyPI `kubric` package has had no release since 2021.
- The BUILD office scans `main` against OSV.dev every night and lists findings on the project's board
  (Security timeline group). Fix critical findings within 2 days, high within 7, medium within 30.
- Before you change a pin, check the new version on OSV.dev, choose a release at least two weeks old,
  and install through the pip gate (`/srv/tool-bin/pip-gate`), which checks hashes, provenance and
  advisories.

### 2026-11-13 sweep: versions changed

| Package | Was | Now | Why |
|---|---|---|---|
| Pillow | 11.3.0 | 13.0.0 | 5 critical (heap overflows, Ghostscript argument injection) and ~55 more |
| torch / torchvision | 2.7.1 / 0.22.1 | 2.14.1 / 0.29.1 | RCE from untrusted checkpoints even with `weights_only` (GHSA-63cw-57p8-fm3p), memory corruption |
| transformers | 4.57.1 | 5.21.1 | RCE and code-before-consent advisories, `save_pretrained` path traversal |
| diffusers | 0.33.1 | 0.42.1 | `trust_remote_code` bypasses (GHSA-7wx4-6vff-v64p, GHSA-98h9-4798-4q5v) |
| accelerate | 1.12.0 | 1.15.0 | sharded-checkpoint path traversal (GHSA-4j2p-28q2-5m79) |
| datasets | 4.0.0 | 5.1.0 | folder-builder path traversal (GHSA-379c-qx7v-6h59) |
| requests | 2.32.5 | 2.34.2 | insecure temp file reuse (GHSA-gc5v-m9x4-r6x2) |
| safetensors | 0.6.2 | 0.8.0 | required by transformers 5.21 and diffusers 0.42 |
| peft | 0.17.1 | 0.21.2 | matches transformers 5 |

Removed: `decord` and the PyPI `kubric` (both unmaintained since 2021; see above), `tomesd` and `torchsde` (unused, unmaintained), `omegaconf` (only used by the removed UI),
`func-timeout` (unmaintained since 2019; replaced by `videox_fun/utils/timeout.py`, standard library
only), and the commented-out Gradio 3.x line (80+ advisories).

The full resolved set for the target (CPython 3.12, Linux aarch64), 144 packages including every
transitive one, had no OSV advisory on 2026-11-13.

## Loading files safely

| Rule | Where it is enforced |
|---|---|
| `torch.load` always passes `weights_only=True` (tensors and plain data only, never arbitrary objects). Prefer `.safetensors` files. | every call site; `tests/test_security.py` |
| Pickle files are read with `safe_pickle.safe_load`, which allows only plain built-in data and NumPy arrays and refuses everything else. | `videox_fun/utils/safe_pickle.py` (copied to `data_generation/safe_pickle.py` for Blender) |
| Training checkpoints save the sampler resume state as `sampler_pos_start.json`. Older checkpoints with `sampler_pos_start.pkl` still resume, read through `safe_load`. | `videox_fun/utils/sampler_state.py` |
| No `trust_remote_code=True`: model repos never run their own code here. | `tests/test_security.py` |
| No `shell=True` and no `exec` of a spliced path. Subprocesses get an argument list. | `tests/test_security.py` |

A HUMOTO `.pkl` holding anything other than plain data and NumPy arrays now stops with
`refusing to load <module>.<name> from a pickle file`. If a legitimate file triggers this, convert it
to plain data (lists, dicts, arrays). Do not widen the allow-list to code-bearing types.

## Removed: unused reward models

`videox_fun/reward/` (inherited from VideoX-Fun; nothing in this repository imported it) was deleted. It
downloaded weights it could not verify: Hugging Face models without a pinned revision (Bandit B615), a
checkpoint from an object-storage bucket checked only by MD5, and a `.pth` from a GitHub `main` branch
with no checksum. If reward-guided training is added later, pin every model to a commit and every file
to a SHA-256.

## Removed: unauthenticated web API and Gradio UI

`videox_fun/api/` and `videox_fun/ui/` (inherited from VideoX-Fun) were deleted. They were not
importable here: they referenced a missing `controller` module and Gradio was not installed. They
offered unauthenticated FastAPI routes that:

- loaded any model path the caller named (code execution through a checkpoint);
- fetched any URL the caller gave (server-side request forgery);
- returned any file path base64-encoded.

If a demo UI is wanted again, build it with a login, loopback binding by default and the Security
Self-Check page.

## The Streamlit review tool

`data_generation/.streamlit/config.toml` binds `physics_review_ui.py` to `127.0.0.1`, keeps CORS and
XSRF protection on, allows only the Host names `localhost` and `127.0.0.1` on its WebSocket
(`server.allowedHosts`), and turns off usage statistics. Reach it from elsewhere over an SSH tunnel.

It was assessed against the Security Self-Check standard on 2026-11-13: `conformance/void-model.toml` in
`chappa-ai-llc/security-self-check`. Probed live (Streamlit 1.66.1):

| Probe | Result |
|---|---|
| Connect on the machine's own network address | refused (loopback only) |
| WebSocket with `Host: rebind.evil.example` (DNS rebinding) | 403 |
| WebSocket with `Origin: https://evil.example` (cross-site) | 403 |
| WebSocket from `127.0.0.1` or `localhost` | 101 (works) |
| `/.env`, `/.git/HEAD`, `/physics_review_ui.py` | the app shell, never a file |
| Version in any answer | none |

Streamlit cannot send security headers (CSP, frame protection, `nosniff`), and the tool has no sign-in.
Both are accepted for a single-user tool on loopback. Board decision D-01 covers whether to do more.

## Notebook

`notebook.ipynb` used to clone the upstream `netflix/void-model`, which installs upstream's old pins.
It now clones this repository.

## SAM2

SAM2 publishes no release tags, so the README installs it from Git at a pinned commit (`2b90b9f`, the
head of `main` on 2026-11-13). At that commit SAM2 loads its checkpoint with
`torch.load(..., weights_only=True)` (`sam2/build_sam.py`), so a checkpoint file cannot run code.

## Known items left open

- None in the code or dependencies as of 2026-11-13.
- The target check passed on sparky-1 on 2026-11-13 (BUILD office task `void-model-target-check`, run 350, tag
  v1.2.1-offline-arm64): Python 3.12.3 on aarch64, the 143-wheel hash lock installed, `pip check` clean, tests
  26/26, torch 2.14.1+cu130 with CUDA 13.0 on the NVIDIA GB10, and the CUDA smoke test OK.

## Checking it yourself

```bash
python -m unittest discover -s tests -v
bandit -r . -x ./scratchpad,./tests -ll
```

On 2026-11-13 Bandit 1.9.4 found no high or medium issues. The low ones are expected here: `random` for data
augmentation, `subprocess` with argument lists (ffmpeg, Blender), `assert`, and `import pickle` in the safe
loaders.

### On the target (DGX Spark)

`requirements-lock-linux-aarch64-cp312.txt` is the exact install set for CPython 3.12 on Linux aarch64: 143 wheels,
each pinned by version and SHA-256, every one checked on OSV.dev (deepspeed is left out because it ships only as
source). `tools/target_check.sh` installs it into a fresh venv with `--require-hashes --no-deps`, runs `pip check`,
the test suite and a CUDA smoke test (tiny transformer with rotary embeddings and VAE in bf16 on the GPU), and
prints PASS or FAIL. The BUILD office task `void-model-target-check` runs it on sparky-1 once the owner approves
it on the Tasks page.

```bash
bash tools/target_check.sh
```

### GitHub alerts

- **Dependabot:** on. The office's dependency report reads the open alerts each run
  (`GET /repos/chappa-ai-llc/void-model/dependabot/alerts?state=open`, tool-bin `dep-audit/dep_audit.py`
  `dependabot_alerts`; a failed read is recorded as `enabled: false` with the error). On 2026-11-13 15:38Z
  (main@aa5bc1e) the read succeeded and returned no open alert; 72 were open when the project was adopted.
- **Code scanning:** CodeQL would need GitHub Actions, which chappa.ai does not use. Bandit (above) and the
  tests stand in for it.
- **Secret scanning:** gitleaks over the full history (47 commits on 2026-11-13) found nothing; the secret
  gate checks every push.

## Reporting a vulnerability

Post on the BUILD office forum to `void-model` and `owner`. Do not disclose an unfixed vulnerability
in public.
