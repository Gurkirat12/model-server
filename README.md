# model-server

A profile-driven inference server for TinyLlama 1.1B, exposing an OpenAI-compatible HTTP API. Profiles are selected at deploy time via the `PROFILE` environment variable.

## How to Build

```bash
git clone <repo-url>
cd model-server
docker build -t model-server:latest .
```

> First build downloads TinyLlama Q4_K_M GGUF (~668 MB) and compiles llama-cpp-python. Takes ~15-20 min. Subsequent builds use cache.

## How to Run Each Profile

```bash
docker run -e PROFILE=balanced   -p 8000:8000 model-server:latest
docker run -e PROFILE=throughput -p 8000:8000 model-server:latest
docker run -e PROFILE=latency    -p 8000:8000 model-server:latest
```

Invalid profile fails fast:
```bash
docker run -e PROFILE=fast -p 8000:8000 model-server:latest
# FATAL: PROFILE='fast' is not a valid profile.
# Valid values: balanced throughput latency
```

Wait for model to load before sending requests:
```bash
until curl -sf http://localhost:8000/v1/health/ready; do sleep 2; done
```

## curl Examples

```bash
# Liveness
curl http://localhost:8000/v1/health/live

# Readiness
curl http://localhost:8000/v1/health/ready

# List models
curl http://localhost:8000/v1/models | jq .

# Active profile
curl http://localhost:8000/v1/profiles | jq .

# Chat completion
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "system", "content": "You are a helpful assistant."},
      {"role": "user", "content": "What is the capital of France?"}
    ],
    "max_tokens": 100
  }' | jq .choices[0].message.content

# In-container CLI
docker exec <container_name> list-profiles
```

## OpenAI Python Client

```bash
pip install openai
```

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="not-needed",
)

response = client.chat.completions.create(
    model="TinyLlama-1.1B-Chat",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Explain Docker in one sentence."},
    ],
    max_tokens=150,
)
print(response.choices[0].message.content)
```

## Verifying Profile Behavior Differs

| Parameter | latency | balanced | throughput |
|-----------|---------|----------|------------|
| `n_ctx` | 512 | 1536 | 2048 |
| `n_batch` | 64 | 256 | 512 |
| `max_concurrent_requests` | 1 | 2 | 4 |
| `max_tokens` default | 256 | 512 | 1024 |

Check active profile parameters:
```bash
curl -s http://localhost:8000/v1/profiles | jq '{active: .active_profile, n_ctx: .profiles[.active_profile].n_ctx, n_batch: .profiles[.active_profile].n_batch}'
```

Verify concurrency difference (latency serializes, throughput parallelizes):
```bash
for i in 1 2 3 4; do
  curl -s -X POST http://localhost:8000/v1/chat/completions \
    -H "Content-Type: application/json" \
    -d '{"messages": [{"role": "user", "content": "Count to 10."}], "max_tokens": 50}' &
done
wait
```

## Run Tests

```bash
chmod +x test.sh
./test.sh
```

## Tradeoffs and Decisions

**Model: TinyLlama Q4_K_M GGUF** — smallest chat-capable model at ~668MB. Fits well within 5GB image limit. Larger models (Phi-3 3.8B) would give better answers but be 3x slower on CPU.

**Runtime: llama-cpp-python** — chosen over transformers because GGUF quantization reduces memory and improves CPU speed. n_ctx/n_batch knobs map directly to profile parameters. vLLM is GPU-first and not suitable here.

**Profile mechanism** — max_concurrent_requests semaphore is the clearest observable difference under concurrent load. n_ctx and n_batch are set at model init time, meaning profile switching requires container restart (by design per spec).

**What I'd do differently with more time:**
- Add streaming (llama-cpp-python supports it natively)
- Mount model from volume instead of baking into image (keeps image ~200MB)
- Expose n_threads as manifest parameter (hardware-dependent, not profile-dependent)
- Add API key authentication for production use

**One pushback on the spec:** Profile validation exists in both entrypoint.sh (bash, fast) and config.py (Python, authoritative). The manifest-derived check in config.py is the single source of truth. The entrypoint check is a convenience for operators to get fast feedback without waiting for Python startup.

## Time Spent

| Phase | Time |
|-------|------|
| Model + runtime selection | ~45 min |
| Profile system + endpoints | ~50 min |
| Dockerfile | ~30 min |
| CLI + entrypoint | ~20 min |
| test.sh | ~25 min |
| README | ~30 min |
| **Total** | **~3h 20min** |
