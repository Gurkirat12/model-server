import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import List, Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel

from config import load_manifest, resolve_profile

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("model-server")

_model = None
_model_loaded: bool = False
_active_profile: str = ""
_profile_config: dict = {}
_manifest: dict = {}
_semaphore: Optional[asyncio.Semaphore] = None

MODEL_DIR = os.environ.get("MODEL_DIR", "/opt/app/models")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _model, _model_loaded, _active_profile, _profile_config, _manifest, _semaphore

    _manifest = load_manifest()
    _active_profile, _profile_config = resolve_profile(_manifest)

    logger.info(f"Profile     : {_active_profile}")
    logger.info(f"n_ctx       : {_profile_config['n_ctx']}")
    logger.info(f"n_batch     : {_profile_config['n_batch']}")
    logger.info(f"max_concur  : {_profile_config['max_concurrent_requests']}")

    _semaphore = asyncio.Semaphore(_profile_config["max_concurrent_requests"])

    model_file = os.path.join(MODEL_DIR, _manifest["model"]["file"])
    logger.info(f"Loading model from {model_file} ...")

    try:
        from llama_cpp import Llama
        loop = asyncio.get_event_loop()
        _model = await loop.run_in_executor(
            None,
            lambda: Llama(
                model_path=model_file,
                n_ctx=_profile_config["n_ctx"],
                n_batch=_profile_config["n_batch"],
                verbose=False,
                n_threads=os.cpu_count(),
            ),
        )
        _model_loaded = True
        logger.info("Model loaded. Server is ready.")
    except Exception as exc:
        logger.error(f"Model load failed: {exc}")

    yield

    logger.info("Shutting down — draining requests...")
    _model_loaded = False
    _model = None
    logger.info("Shutdown complete.")


app = FastAPI(title="Model Server", lifespan=lifespan)


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: Optional[str] = None
    messages: List[ChatMessage]
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    stream: Optional[bool] = False


@app.post("/v1/chat/completions")
async def chat_completions(req: ChatCompletionRequest):
    if not _model_loaded:
        raise HTTPException(status_code=503, detail="Model not ready")

    if req.stream:
        raise HTTPException(status_code=400, detail="Streaming not supported")

    prompt = _build_prompt(req.messages)
    gen = _profile_config["generation"]
    max_tokens = req.max_tokens if req.max_tokens is not None else gen["max_tokens"]
    temperature = req.temperature if req.temperature is not None else gen["temperature"]
    top_p = req.top_p if req.top_p is not None else gen["top_p"]

    async with _semaphore:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: _model(
                prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
                repeat_penalty=gen.get("repeat_penalty", 1.1),
                echo=False,
                stop=["</s>", "<|user|>", "<|system|>"],
            ),
        )

    choice = result["choices"][0]
    usage = result.get("usage", {})
    model_name = _manifest["model"]["name"]

    return {
        "id": f"chatcmpl-{int(time.time() * 1000)}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model_name,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": choice["text"].strip(),
                },
                "finish_reason": choice.get("finish_reason", "stop"),
            }
        ],
        "usage": {
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
        },
    }


@app.get("/v1/models")
async def list_models():
    model_info = _manifest.get("model", {}) if _manifest else {}
    return {
        "object": "list",
        "data": [
            {
                "id": model_info.get("name", "unknown"),
                "object": "model",
                "created": 1700000000,
                "owned_by": "local",
                "root": model_info.get("source", ""),
                "parent": None,
                "permission": [],
            }
        ],
    }


@app.get("/v1/health/ready")
async def health_ready(response: Response):
    if _model_loaded:
        return {"status": "ready", "profile": _active_profile}
    response.status_code = 503
    return {"status": "not_ready", "reason": "model loading in progress"}


@app.get("/v1/health/live")
async def health_live():
    return {"status": "live"}


@app.get("/v1/profiles")
async def get_profiles():
    return {
        "active_profile": _active_profile,
        "profiles": _manifest.get("profiles", {}),
    }


def _build_prompt(messages: List[ChatMessage]) -> str:
    parts = []
    for msg in messages:
        if msg.role == "system":
            parts.append(f"<|system|>\n{msg.content}</s>")
        elif msg.role == "user":
            parts.append(f"<|user|>\n{msg.content}</s>")
        elif msg.role == "assistant":
            parts.append(f"<|assistant|>\n{msg.content}</s>")
    parts.append("<|assistant|>")
    return "\n".join(parts)


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        log_config=None,
    )
