"""Choose the VLM backend for stage 2 of the mask pipeline.

The offline edition defaults to a local OpenAI-compatible server (vLLM on 127.0.0.1:8000) serving
Gemma 4 31B, so footage never leaves the machine. Google's Gemini API is opt-in with
``--vlm-backend gemini`` and a key read from the file named by ``GEMINI_API_KEY_FILE``.
"""

import os
import sys
from dataclasses import dataclass
from typing import Optional

BACKENDS = ("vllm", "ollama", "llama.cpp", "gemini")
DEFAULT_BACKEND = "vllm"
DEFAULT_SERVER = "127.0.0.1"
DEFAULT_LOCAL_MODEL = "google/gemma-4-31b-it"
DEFAULT_GEMINI_MODEL = "gemini-3-pro-preview"
DEFAULT_PORTS = {"vllm": 8000, "ollama": 11434, "llama.cpp": 8080}
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
# Local servers ignore the key, but the OpenAI client refuses an empty one.
LOCAL_PLACEHOLDER_KEY = "local-no-key"


@dataclass(frozen=True)
class VlmSettings:
    backend: str
    base_url: str
    api_key: str
    model: str

    @property
    def sends_video(self) -> bool:
        """Only Gemini accepts a whole video as a data URL; local servers get the frame grids."""
        return self.backend == "gemini"


def read_secret(name: str, environ=os.environ) -> Optional[str]:
    """Read a secret from the file named by ``<name>_FILE`` (Docker secrets style).

    The plain ``<name>`` variable still works, so older setups keep running, but it prints a warning:
    an environment variable leaks into process listings and child processes.
    """
    path = environ.get(f"{name}_FILE")
    if path:
        with open(path, "r", encoding="utf-8") as fh:
            value = fh.read().strip()
        if not value:
            raise RuntimeError(f"{name}_FILE points to an empty file: {path}")
        return value
    value = environ.get(name)
    if value:
        print(f"WARNING: {name} is read from the environment; put it in a file and set {name}_FILE instead.",
              file=sys.stderr)
        return value
    return None


def resolve_settings(backend: str = DEFAULT_BACKEND, server: str = DEFAULT_SERVER, port: Optional[int] = None,
                     model: Optional[str] = None, environ=os.environ) -> VlmSettings:
    """Turn the command-line choices into a base URL, key and model name. No network access."""
    if backend not in BACKENDS:
        raise ValueError(f"unknown VLM backend {backend!r}; choose one of {', '.join(BACKENDS)}")
    if backend == "gemini":
        key = read_secret("GEMINI_API_KEY", environ)
        if not key:
            raise RuntimeError("--vlm-backend gemini needs a Google AI key: write it to a file and set "
                               "GEMINI_API_KEY_FILE to that path. Local backends need no key.")
        return VlmSettings("gemini", GEMINI_BASE_URL, key, model or DEFAULT_GEMINI_MODEL)
    if not server or any(c in server for c in "/@?# "):
        raise ValueError(f"--vlm-server must be a host name or IP address, got {server!r}")
    host = f"[{server}]" if ":" in server else server
    base_url = f"http://{host}:{port or DEFAULT_PORTS[backend]}/v1"
    return VlmSettings(backend, base_url, LOCAL_PLACEHOLDER_KEY, model or DEFAULT_LOCAL_MODEL)


def make_client(settings: VlmSettings):
    import openai  # imported here so resolve_settings() can be tested without the client installed

    return openai.OpenAI(api_key=settings.api_key, base_url=settings.base_url)


def add_arguments(parser) -> None:
    """Add the --vlm-* options. The --analysis-self-host-* and --model names of 1.2.x still parse."""
    parser.add_argument("--vlm-backend", "--analysis-self-host-type", dest="vlm_backend", choices=BACKENDS,
                        default=DEFAULT_BACKEND,
                        help=f"VLM server type (default {DEFAULT_BACKEND}: a local server, nothing leaves the machine)")
    parser.add_argument("--vlm-server", "--analysis-self-host-server", dest="vlm_server", default=DEFAULT_SERVER,
                        help=f"host of the local VLM server (default {DEFAULT_SERVER})")
    parser.add_argument("--vlm-port", "--analysis-self-host-port", dest="vlm_port", type=int,
                        help="port of the local VLM server (default: vllm 8000, ollama 11434, llama.cpp 8080)")
    parser.add_argument("--vlm-model", "--analysis-self-host-model", "--model", dest="vlm_model",
                        help=f"model name the server knows (default {DEFAULT_LOCAL_MODEL}; "
                             f"{DEFAULT_GEMINI_MODEL} for gemini)")
