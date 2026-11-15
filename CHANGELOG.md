# Changelog

All notable changes to the Chappa AI offline edition of VOID. Versions are tagged on `main` as
`v<semver>-offline-arm64`.

## 1.3.0-offline-arm64 — 2026-11-15

### Fixed
- The mask pipeline's stage 2 (`VLM-MASK-REASONER/stage2_vlm_analysis.py`) runs again. It crashed on
  start, and needed a Google key even for a local server (#4).
- `openai`, which stage 2 imports, is now in `requirements.txt` (`openai==3.42.1`) and the hash lock (with
  `jiter` 0.18.0 and `sniffio` 1.3.1; 146 wheels).

### Changed
- Stage 2 asks a local VLM server by default: vLLM on `127.0.0.1:8000`, model `google/gemma-4-31b-it`.
  Footage stays on the machine and no key is needed. `--vlm-backend ollama|llama.cpp|gemini`,
  `--vlm-server`, `--vlm-port` and `--vlm-model` choose another; `run_pipeline.sh` passes them through.
- Local servers get the frame grids only; only Gemini is also sent the whole video.
- `test_gemini_video.py` checks whichever backend stage 2 will use.

### Security
- Google's Gemini API is opt-in, and its key is read from the file named by `GEMINI_API_KEY_FILE`.
- Removed `stage2_vlm_analysis_cf.py`, which sent footage to upstream's private Cloudflare AI gateway.
- The reasoner README installs SAM2 at the same pinned commit as the main README.

### Upgrading
- Start a VLM server before the pipeline (`vllm serve google/gemma-4-31b-it --host 127.0.0.1 --port 8000`),
  or pass `--vlm-backend gemini` to keep using Google.
- If you use Gemini, move the key into a file and set `GEMINI_API_KEY_FILE`. `GEMINI_API_KEY` still
  works, with a warning.
- The 1.2.x option names (`--analysis-self-host-type`, `-server`, `-port`, `-model`, `--model`) still work.
- Reinstall from `requirements.txt` or the lock to get `openai`.

## 1.2.1-offline-arm64 — 2026-11-13

### Added
- `requirements-lock-linux-aarch64-cp312.txt`: the hash-locked install set for the DGX Spark target.
- `tools/target_check.sh`: install that lock in a fresh venv, run the tests and a CUDA smoke test.

### Security
- The Streamlit review tool accepts WebSocket connections only for the Host names `localhost` and
  `127.0.0.1` (`server.allowedHosts`), which blocks DNS rebinding. Assessed against the Security Self-Check
  standard (`security-self-check` conformance/void-model.toml).

## 1.2.0-offline-arm64 — 2026-11-13

### Changed
- Video decoding in the training loaders uses PyAV (`av==19.0.1`) instead of decord, which has had no release
  since 2021 and needed this project's custom ARM64 wheel. `videox_fun/utils/video_reader.py` keeps decord's
  interface. Its frames are identical to decord 0.6.0 on the sample videos.
- The Kubric generator runs in Kubric's Docker image pinned by digest. `data_generation/requirements-kubric.txt`
  (PyPI kubric 0.1.1, from 2021) is removed.

### Upgrading
- Reinstall from `requirements.txt`: `av` replaces `decord`, and nothing is downloaded from a GitHub release any
  more.

## 1.1.1-offline-arm64 — 2026-11-13

### Security
- Removed `videox_fun/reward/`, which nothing used. It downloaded Hugging Face models without a pinned
  revision (Bandit B615) and weights checked only by MD5 or not at all.
- Bandit 1.9.4 now finds no high or medium issue (see docs/SECURITY.md, "Checking it yourself").

## 1.1.0-offline-arm64 — 2026-11-13

Security sweep. Details and the reasons for each change: [docs/SECURITY.md](docs/SECURITY.md).

### Security
- Fixed all 82 open dependency advisories (5 critical, 43 high): Pillow 13.0.0, torch 2.14.1 and
  torchvision 0.29.1, transformers 5.21.1, diffusers 0.42.1, accelerate 1.15.0, datasets 5.1.0,
  requests 2.34.2 (with safetensors 0.8.0 and peft 0.21.2 to match).
- `torch.load` always uses `weights_only=True`; pickle files are read through a restricted loader
  (`safe_pickle.safe_load`); no `trust_remote_code=True` anywhere.
- Removed `videox_fun/api/` and `videox_fun/ui/`: unauthenticated FastAPI/Gradio routes that loaded any
  model path, fetched any URL and returned any file. They were not importable (missing `controller`).
- The Blender fallback in `data_generation/convert_all_scenarios_for_characters.py` no longer splices a
  path into `exec(...)` code.
- The Streamlit physics review UI listens on 127.0.0.1 only, with usage statistics off.
- The notebook clones this repository, not upstream's older pins.
- Every requirement is pinned with `==`; the ARM64 decord wheel is pinned by SHA-256.

### Changed
- Training checkpoints save the sampler resume state as `sampler_pos_start.json`; older
  `sampler_pos_start.pkl` files still resume (read safely).
- `huggingface-cli` is gone from huggingface_hub 1.0 and later: the README uses `hf download`.
- Kubric's dependencies moved to `data_generation/requirements-kubric.txt` (replaced in 1.2.0).

### Removed
- Unmaintained or unused packages: `func-timeout` (replaced by `videox_fun/utils/timeout.py`), `tomesd`,
  `torchsde`, `omegaconf`.

### Upgrading
- Recreate your environment: `pip install -r requirements.txt` (transformers 5 and huggingface_hub 2 are
  major upgrades). Python 3.11 or later is required by Pillow 13 and torch 2.14.
