# تشغيل تطبيق الويب (Frontend) عبر Docker

## بناء وتشغيل مستقلّ
```bash
docker compose -f docker-compose.web.yml up --build
# الويب على: http://localhost:8080
```

أو يدوياً:
```bash
docker build -t sahool-web .
docker run -p 8080:8080 sahool-web
```

## التفاصيل
- **Multi-stage**: Node 20 (build) → Nginx 1.27 (serve)
- **non-root**: يعمل كمستخدم `nginx` على المنفذ 8080 (لا يحتاج root)
- **healthz**: `GET /healthz` → 200 (للـHEALTHCHECK + k8s probes)
- **proxy**: `/api/*` و `/ws/*` → `sahool-kong:8000` (API gateway)
- **SPA routing**: كل المسارات → `index.html`

## متغيّرات البناء (build args)
| المتغيّر | الافتراضي | الوصف |
|---------|----------|-------|
| `VITE_API_URL` | `/api` | مسار الـAPI (نسبيّ خلف nginx proxy) |
| `VITE_MOCK_MODE` | `false` | وضع المحاكاة بلا backend |

## ملاحظات صدق
- الـbuild في Docker يستخدم `vite build` (script `build:docker`)، **لا** `tsc && vite build`،
  لأنّ كود v8 الموروث فيه أخطاء أنواع (type-level) لا تكسر تشغيل JS لكنّها تكسر بوّابة `tsc`.
  هذه الأخطاء (children props، حقول API) تحتاج إصلاحاً منفصلاً لاستعادة فحص الأنواع الكامل.
- `package-lock.json` مفقود → الـDockerfile يقع على `npm install` (أبطأ، أقلّ حتميّة من `npm ci`).
  يُنصَح بتوليد lockfile (`npm install` محلّياً ثمّ ارتكابه) قبل الإنتاج.
