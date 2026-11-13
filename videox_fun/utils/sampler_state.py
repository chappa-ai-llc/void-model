"""Read the batch sampler's resume state saved beside a training checkpoint.

Checkpoints written by this version store ``[pos_start, first_epoch]`` in
``sampler_pos_start.json``. Older checkpoints stored it as
``sampler_pos_start.pkl``; those are still read, but through
``safe_pickle.safe_load`` so a tampered checkpoint folder cannot run code.
"""

import json
import os

from .safe_pickle import safe_load

JSON_NAME = "sampler_pos_start.json"
LEGACY_PICKLE_NAME = "sampler_pos_start.pkl"


def load_sampler_state(checkpoint_dir):
    """Return ``(pos_start, first_epoch)`` as ints, or None when no state was saved."""
    json_path = os.path.join(checkpoint_dir, JSON_NAME)
    pkl_path = os.path.join(checkpoint_dir, LEGACY_PICKLE_NAME)
    if os.path.exists(json_path):
        with open(json_path, "r") as file:
            state = json.load(file)
    elif os.path.exists(pkl_path):
        with open(pkl_path, "rb") as file:
            state = safe_load(file)
    else:
        return None
    if not isinstance(state, (list, tuple)) or len(state) != 2:
        raise ValueError(f"unexpected sampler state in {checkpoint_dir}: {state!r}")
    pos_start, first_epoch = state
    return int(pos_start), int(first_epoch)
