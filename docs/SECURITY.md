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

- Every requirement in `requirements.txt`, `data_generation/requirements.txt` and
  `data_generation/requirements-kubric.txt` is pinned with `==`. The ARM64 decord wheel is a direct URL
  pinned by `#sha256=`, so pip refuses a changed file. `tests/test_security.py` fails on an unpinned line.
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

Removed: `tomesd` and `torchsde` (unused, unmaintained), `omegaconf` (only used by the removed UI),
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
XSRF protection on, and turns off usage statistics. Reach it from elsewhere over an SSH tunnel.

## Notebook

`notebook.ipynb` used to clone the upstream `netflix/void-model`, which installs upstream's old pins.
It now clones this repository.

## Known items left open

- SAM2 is installed from its Git repository (README, "Install SAM2") without a pinned commit. Pin it
  when the project settles on a SAM2 version.
- The MPS reward model download (`videox_fun/reward/reward_fn.py`) is checked by MD5, as upstream
  publishes it. Replace with SHA-256 when a trusted hash is available. Training-only code path.

## Checking it yourself

```bash
python -m unittest discover -s tests -v
```

## Reporting a vulnerability

Post on the BUILD office forum to `void-model` and `owner`. Do not disclose an unfixed vulnerability
in public.
