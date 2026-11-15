# VLM Mask Reasoner — Mask Generation Pipeline

Generates quadmasks for video inpainting by combining user-guided SAM2 segmentation with scene reasoning by a vision-language model (VLM). By default the VLM is Gemma 4 31B on a local server, so footage never leaves the machine. The output `quadmask_0.mp4` encodes four semantic layers that the inpainting model uses to understand what to remove and what to preserve.

---

## Quadmask Values

| Value | Meaning |
|-------|---------|
| `0` | Primary object (to be removed) |
| `63` | Overlap of primary and affected regions |
| `127` | Affected objects (shadows, reflections, held items) |
| `255` | Background — keep as-is |

---

## Step 1 — Select Points via GUI

Launch the point selector GUI:

```bash
python point_selector_gui.py
```

Use this GUI to place sparse click points on the object(s) you want removed.

**A few things to know:**

- Points can be placed on **any frame**, not just the first. If the object you want to remove only appears later in the video, navigate to that frame and click there.
- You can place points across **multiple frames** — useful when there are multiple distinct objects to remove, or when an object's position shifts significantly over time.
- The GUI saves your selections to a `config_points.json` file. Keep track of where this is saved — you'll pass it to the pipeline next.

---

## Step 2 — Run the Pipeline

Once you have your `config_points.json`, run all stages with a single command:

```bash
bash run_pipeline.sh <config_points.json>
```

Optional flags:

```bash
bash run_pipeline.sh <config_points.json> \
    --sam2-checkpoint ../sam2_hiera_large.pt \
    --device cuda \
    --vlm-backend vllm --vlm-server 127.0.0.1 --vlm-port 8000 --vlm-model google/gemma-4-31b-it
```

The `--vlm-*` values above are the defaults. See [Installation, step 3](#3-vlm-server) for the choices.

This runs four stages automatically:

1. **Stage 1 — SAM2 Segmentation:** Propagates your point clicks into a per-frame black mask for the primary object.
2. **Stage 2 — VLM Analysis:** Asks the VLM server (local by default) to analyze the scene to identify affected objects — things like shadows, reflections, or items the primary object is interacting with.
3. **Stage 3 — Grey Mask Generation:** Produces a grey mask track for the affected objects identified in Stage 2.
4. **Stage 4 — Combine into Quadmask:** Merges the black and grey masks into the final `quadmask_0.mp4`.

The output `quadmask_0.mp4` is written into each video's `output_dir` as specified in the config.

> **Note on grey values in frame 1:** The inpainting model was trained with grey-valued regions (`127`) starting from frame 1 onward — not on the very first frame. We find this convention improves inference quality, so the pipeline automatically clears any grey pixels from frame 0 of the final quadmask before saving.

---

## Step 3 (Optional) — Manual Mask Correction

If the generated quadmask needs refinement, you can correct it interactively:

```bash
python edit_quadmask.py
```

Point the GUI to the folder containing `quadmask_0.mp4`. You can paint over regions frame-by-frame to fix any mask errors before running inference. The corrected mask is saved back to `quadmask_0.mp4` in the same folder.

---

## Installation & Dependencies

### 1. Python dependencies

Install the main requirements from the repo root:

```bash
pip install -r requirements.txt
```

### 2. SAM2

SAM2 must be installed separately (it is not on PyPI). It publishes no release tags, so install it pinned to a commit, exactly as in the main README's Setup section (`sam2` at `2b90b9f5ceec907a1c18123530e92e794ad901a4`, the head of its `main` branch on 2026-11-13, dated 2024-12-16).

Then download the SAM2 checkpoint. The pipeline defaults to `sam2_hiera_large.pt` one level above this directory:

```bash
# from the repo root (or wherever you want to store it)
wget https://dl.fbaipublicfiles.com/segment_anything_2/072824/sam2_hiera_large.pt
```

If you place the checkpoint elsewhere, pass it explicitly:

```bash
bash run_pipeline.sh config_points.json --sam2-checkpoint /path/to/sam2_hiera_large.pt
```

> SAM2 requires **Python ≥ 3.10** and **PyTorch ≥ 2.3.1** with CUDA. See the [SAM2 repo](https://github.com/facebookresearch/sam2) for full system requirements.

### 3. VLM server

Stage 2 sends frame grids to an OpenAI-compatible server and reads back JSON. The default is a vLLM server on this machine, serving `google/gemma-4-31b-it` (the model the main README's Setup section downloads). vLLM is not in `requirements.txt`; install it separately and bind it to loopback:

```bash
vllm serve google/gemma-4-31b-it --host 127.0.0.1 --port 8000
```

| `--vlm-backend` | Default address | Default `--vlm-model` | Key |
|---|---|---|---|
| `vllm` (default) | `127.0.0.1:8000` | `google/gemma-4-31b-it` | none |
| `ollama` | `127.0.0.1:11434` | `google/gemma-4-31b-it`: pass the tag `ollama list` shows instead | none |
| `llama.cpp` | `127.0.0.1:8080` | `google/gemma-4-31b-it`: pass the name your server reports | none |
| `gemini` | Google's API | `gemini-3-pro-preview` | the file named by `GEMINI_API_KEY_FILE` |

Use `--vlm-server` and `--vlm-port` for a server on another host. Local backends get the frame grids only; only `gemini` is also sent the whole video.

Check that the server answers before a long run (same `--vlm-*` options as the pipeline):

```bash
python test_gemini_video.py --video path/to/video.mp4
```

**Google's Gemini API (opt-in).** `--vlm-backend gemini` sends your footage to Google. Keep the key in a file only you can read, and name the file:

```bash
export GEMINI_API_KEY_FILE="$HOME/.config/void/gemini_api_key"
```

The older `GEMINI_API_KEY` variable still works but prints a warning, because an environment variable is visible to child processes.
