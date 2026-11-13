"""Read video frames by index with PyAV, as a drop-in for the parts of ``decord.VideoReader`` this project used.

decord (last release 2021) is unmaintained and needed a custom ARM64 build. PyAV is maintained and ships FFmpeg in
its wheels for Linux x86_64 and aarch64. Only this surface is provided, because only it was used:

    vr = VideoReader(path, num_threads=2)
    len(vr)                                   # number of frames
    vr.get_batch([0, 4, 8]).asnumpy()         # uint8 array (N, H, W, 3), RGB

``len`` counts the stream's packets without decoding. ``get_batch`` decodes from the start up to the last frame
asked for and converts only the frames asked for, so memory stays at the size of the batch. On the repository's
sample videos the frames match decord 0.6.0 exactly (tests/test_smoke_models.py).
"""

import numpy as np

import av

__all__ = ["VideoReader"]


class _Batch:
    def __init__(self, array):
        self._array = array

    def asnumpy(self):
        return self._array


class VideoReader:
    def __init__(self, path, num_threads=0, **_ignored):
        self._path = str(path)
        self._threads = int(num_threads or 0)
        self._length = None

    def _open(self):
        container = av.open(self._path)
        if not container.streams.video:
            container.close()
            raise ValueError(f"no video stream in {self._path}")
        stream = container.streams.video[0]
        stream.thread_type = "AUTO"
        if self._threads > 0:
            stream.codec_context.thread_count = self._threads
        return container, stream

    def __len__(self):
        if self._length is None:
            container, stream = self._open()
            with container:
                self._length = sum(1 for packet in container.demux(stream) if packet.size)
        return self._length

    def get_batch(self, indices):
        idx = [int(i) for i in np.asarray(indices).reshape(-1)]
        n = len(self)
        idx = [i + n if i < 0 else i for i in idx]
        for i in idx:
            if not 0 <= i < n:
                raise IndexError(f"frame {i} out of range for {n} frames in {self._path}")
        if not idx:
            return _Batch(np.empty((0, 0, 0, 3), dtype=np.uint8))
        wanted, last, found = set(idx), max(idx), {}
        container, stream = self._open()
        with container:
            for position, frame in enumerate(container.decode(stream)):
                if position in wanted:
                    found[position] = frame.to_ndarray(format="rgb24")
                if position >= last:
                    break
        missing = wanted - found.keys()
        if missing:
            raise IndexError(f"frames {sorted(missing)[:5]} could not be decoded from {self._path}")
        return _Batch(np.stack([found[i] for i in idx]))

    def __getitem__(self, index):
        return _Batch(self.get_batch([index]).asnumpy()[0])
