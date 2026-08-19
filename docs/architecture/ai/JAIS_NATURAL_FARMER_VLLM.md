# Jais Natural Farmer — vLLM runtime

This component is a GPU inference runtime, not a new domain authority. It serves
`Solshine/Jais-adapted-7B-Reflection-Tuning-Natural-Farmer` through vLLM's
OpenAI-compatible API and exposes it to SAHOOL under the stable served-model name
`jais-natural-farmer`.

The runtime is selected globally with `AI_PROVIDER=vllm`; `AI_MODEL` may remain empty so the provider-specific default `jais-natural-farmer` is selected. Generation-capable SAHOOL
services receive the same `VLLM_BASE_URL`, `VLLM_API_KEY`, and `VLLM_MODEL` values
from Compose. Retrieval/embedding authority is unchanged; this component only owns
model inference runtime.

Start it with the GPU profile:

```bash
docker compose -f docker-compose.v9.yml -f docker-compose.v9.gpu.yml --profile vllm up -d sahool-vllm-jais
```

Readiness is vLLM `/health`; the OpenAI-compatible chat endpoint is
`/v1/chat/completions`. The service is internal-only and publishes no host port.
