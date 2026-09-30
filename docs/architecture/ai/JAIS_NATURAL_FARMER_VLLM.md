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

## When the runtime is absent (measured, `VLLM-JAIS-FALLBACK-UNPROVEN-01`)

There is **no Ollama fallback**. `AI_PROVIDER=vllm` selects one provider; when
`sahool-vllm-jais` is unreachable (connection refused, DNS failure, timeout) or
answers HTTP >= 400, `ai_generation.generate` returns `None` and the AI Agronomist
serves its evidence-only answer. Ollama is never called. Consequently:

- `/v1/chat` responds `generation_status: "attempted_failed"`, attributes the answer
  to no model (`generation_provider: null`), and names the failed backend in
  `generation_unavailable` (`provider`, `model`, and the observed `runtime` reason
  such as `vllm_unreachable`).
- `/healthz/ai-provider` reports `available: true` for `vllm` only after the server
  has been observed answering (startup probe or a generation call); the latest
  observation is exposed as `vllm_runtime`, so a server started later is picked up
  by the first successful call.
- `/readyz` stays `ready` (generation is optional) and carries the named probe
  receipt in `generation_startup`.

Witness: `tests_v9/test_vllm_jais_fallback_contract.py`. A real fallback to another
backend would be a new capability and needs its own test before it is claimed here.
