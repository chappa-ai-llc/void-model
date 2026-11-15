#!/usr/bin/env python3
"""
Quick VLM smoke test — samples a few frames from a video and asks a simple
question. Use this to check that the VLM backend stage 2 will use answers
before running the full pipeline. It takes the same --vlm-* options as stage 2
(default: local vLLM on 127.0.0.1:8000 serving google/gemma-4-31b-it).

Usage:
    python test_gemini_video.py --video path/to/video.mp4
    python test_gemini_video.py --video path/to/video.mp4 --vlm-backend gemini   # needs GEMINI_API_KEY_FILE
"""

import os
import sys
import base64
import argparse
import cv2
import numpy as np
from pathlib import Path

import vlm_backend


NUM_FRAMES = 4  # keep low for free tier rate limits


def sample_frames(video_path: str, n: int = NUM_FRAMES):
    """Sample n evenly-spaced frames from the video, return as base64 data URLs."""
    cap = cv2.VideoCapture(video_path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    indices = [int(i * (total - 1) / (n - 1)) for i in range(n)]

    data_urls = []
    for idx in indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ret, frame = cap.read()
        if not ret:
            continue
        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        b64 = base64.b64encode(buf).decode("utf-8")
        data_urls.append(f"data:image/jpeg;base64,{b64}")

    cap.release()
    return data_urls


def main():
    parser = argparse.ArgumentParser(description="VLM backend smoke test with video frames")
    parser.add_argument("--video", required=True, help="Path to a video file")
    vlm_backend.add_arguments(parser)
    parser.add_argument("--frames", type=int, default=NUM_FRAMES, help="Number of frames to sample")
    args = parser.parse_args()

    try:
        settings = vlm_backend.resolve_settings(args.vlm_backend, args.vlm_server, args.vlm_port, args.vlm_model)
    except (RuntimeError, ValueError) as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    video_path = Path(args.video)
    if not video_path.exists():
        print(f"ERROR: Video not found: {video_path}")
        sys.exit(1)

    print(f"Video:  {video_path.name}")
    print(f"Server: {settings.backend} at {settings.base_url}")
    print(f"Model:  {settings.model}")
    print(f"Frames: {args.frames}")
    print()

    print(f"Sampling {args.frames} frames...")
    data_urls = sample_frames(str(video_path), args.frames)
    print(f"Got {len(data_urls)} frames. Sending to {settings.backend}...")

    client = vlm_backend.make_client(settings)

    content = [
        {"type": "image_url", "image_url": {"url": url}} for url in data_urls
    ]
    content.append({
        "type": "text",
        "text": "These are evenly-spaced frames from a short video. In one sentence, describe what is happening in the video."
    })

    response = client.chat.completions.create(
        model=settings.model,
        messages=[{"role": "user", "content": content}],
    )

    print("\n--- VLM response ---")
    print(response.choices[0].message.content)
    print("--------------------")
    print("\n✅ The VLM backend answers.")


if __name__ == "__main__":
    main()
