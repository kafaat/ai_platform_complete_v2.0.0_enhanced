# خريطة واجهات SAHOOL (فهرس مسارات ساكن)

مُولّد آليّاً بفحص `@app.route` في كلّ خدمة (offline). للمواصفات الكاملة
(schemas/parameters/responses) شغّل `export_openapi.py` في بيئتك.
**الإجمالي: 123 مسار مباشر · 14 خدمة FastAPI**


## actuator-service — 5 مسار
- `GET /commands`
- `GET /health`
- `GET /healthz`
- `GET /readyz`
- `POST /command`

## agriai-engine — 5 مسار
- `GET /health`
- `GET /healthz`
- `GET /metrics`
- `GET /readyz`
- `POST /v1/recommend`

## auth — 16 مسار
- `GET /auth/me`
- `GET /auth/users`
- `GET /auth/verify`
- `GET /health`
- `GET /healthz`
- `GET /metrics`
- `GET /readyz`
- `PATCH /auth/users/{user_id}/deactivate`
- `PATCH /auth/users/{user_id}/role`
- `POST /auth/change-password`
- `POST /auth/login`
- `POST /auth/logout`
- `POST /auth/password-reset/confirm`
- `POST /auth/password-reset/request`
- `POST /auth/refresh`
- `POST /auth/register`

## edge-inference — 5 مسار
- `GET /healthz`
- `GET /readyz`
- `POST /v1/inference/pest-detect`
- `POST /v1/inference/yield-estimate`
- `POST /v1/sync/trigger`

## guardrails-engine — 7 مسار
- `GET /health`
- `GET /healthz`
- `GET /metrics`
- `GET /readyz`
- `GET /workflow/{workflow_id}`
- `POST /approve/{workflow_id}`
- `POST /validate`

## local-ai-rag — 5 مسار
- `GET /health`
- `GET /healthz`
- `GET /readyz`
- `POST /ingest`
- `POST /query`

## odoo-bridge — 10 مسار
- `GET /config`
- `GET /erp/provider`
- `GET /health`
- `GET /healthz`
- `GET /logs`
- `GET /products`
- `GET /readyz`
- `GET /suppliers`
- `POST /sync`
- `POST /webhook/odoo`

## raster-service — 31 مسار
- `GET /cog/validate`
- `GET /healthz`
- `GET /v1/imagery/best`
- `GET /v1/imagery/dem`
- `GET /v1/imagery/search/landsat`
- `GET /v1/imagery/search/radar`
- `GET /v1/imagery/search/recent`
- `GET /v1/imagery/search/season`
- `GET /imagery/timeseries`
- `GET /info/{layer_id}`
- `GET /jobs/{job_id}`
- `GET /jobs/{job_id}/result`
- `GET /layers/{layer_id}/tilejson`
- `GET /metrics`
- `GET /offline/packs`
- `GET /offline/packs/{pack_name}`
- `GET /readyz`
- `GET /storage/stats`
- `GET /tiles/{layer_id}/{z}/{x}/{y}.png`
- `POST /v1/imagery/search`
- `POST /imagery/timeseries/analyze`
- `POST /imagery/timeseries/parallel`
- `POST /process`
- `POST /process/batch`
- `POST /salinity/calibrate`
- `POST /salinity/classify`
- `POST /storage/cleanup`
- `POST /terrain/slope`
- `POST /upload/drone`
- `POST /upload/raster`
- `POST /zones/classify`

## soil-service — 6 مسار
- `GET /health`
- `GET /healthz`
- `GET /metrics`
- `GET /readyz`
- `GET /soil/readings/{field_id}`
- `POST /soil/ingest`

## supervisor-agent — 8 مسار
- `GET /agent/actuator-audit`
- `GET /agent/journal/{invocation_id}`
- `GET /agent/tools`
- `GET /health`
- `GET /healthz`
- `GET /readyz`
- `POST /agent/optimize`
- `POST /agent/query`

## tts-service — 7 مسار
- `GET /health`
- `GET /healthz`
- `GET /metrics`
- `GET /readyz`
- `GET /tts/voices`
- `POST /tts/stream`
- `POST /tts/synthesize`

## vegetation-analysis-service — 6 مسار
- `GET /health`
- `GET /healthz`
- `GET /metrics`
- `GET /readyz`
- `GET /v1/analyze`
- `GET /v1/timeseries/{field_id}`

## video-processor — 8 مسار
- `DELETE /streams/{stream_id}`
- `GET /health`
- `GET /healthz`
- `GET /readyz`
- `GET /streams`
- `GET /streams/{stream_id}`
- `POST /streams`
- `POST /streams/{stream_id}/snapshot`

## weather-service — 4 مسار
- `GET /`
- `GET /healthz`
- `GET /readyz`
- `GET /weather/{path:path}`
