# ══════════════════════════════════════════════════════════════
# SAHOOL — Frontend (Web) Dockerfile
# Multi-stage: Node.js build → Nginx serve (non-root)
# ══════════════════════════════════════════════════════════════

# ── Stage 1: Build ──────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

# تثبيت الاعتماديات أوّلاً (للاستفادة من Docker layer caching)
# نستخدم سجلّ npm الرسميّ (registry.npmjs.org) — مرآة صينيّة محجوبة/بطيئة عالميّاً.
# .npmrc يُنسخ أوّلاً حتى تكون legacy-peer-deps=true متاحة لـnpm ci.
# npm ci يحتاج package-lock.json؛ لو غاب نقع على npm install
COPY package.json package-lock.json* .npmrc* ./
RUN if [ -f package-lock.json ]; then \
      npm ci --legacy-peer-deps; \
    else \
      echo "⚠ لا package-lock.json — نستخدم npm install" && \
      npm install --legacy-peer-deps; \
    fi

# نسخ الكود وبناء المشروع
COPY . .

# متغيّرات البناء — الصورة تُخدَّم خلف nginx :80 (المرجع القانونيّ)، فالافتراضيّ
# 'gateway' (مسارات نسبيّة) هو الصحيح. لا نُعرّف VITE_*_BASE_URL هنا كي لا تُلغي
# افتراضات الكود الصحيحة؛ نُثبّت الوضع صراحةً فقط. وضع التطوير المباشر يُضبَط
# وقت البناء بـ--build-arg VITE_API_MODE=dev عند الحاجة.
ARG VITE_API_MODE=gateway
ARG VITE_MOCK_MODE=false
# Compose/build callers still pass these names; Vite only reads values available at
# build time, so expose them explicitly instead of relying on runtime container env.
ARG VITE_API_URL=/api
ARG VITE_WS_URL=/ws
ARG VITE_DEV_PROXY_TARGET=http://localhost

ENV VITE_API_MODE=$VITE_API_MODE \
    VITE_MOCK_MODE=$VITE_MOCK_MODE \
    VITE_API_URL=$VITE_API_URL \
    VITE_WS_URL=$VITE_WS_URL \
    VITE_DEV_PROXY_TARGET=$VITE_DEV_PROXY_TARGET

RUN npm run build:docker

# ── Stage 2: Serve (non-root nginx) ─────────────────────────
FROM nginx:1.27-alpine

# نسخ ملفّات البناء
COPY --from=builder /app/dist /usr/share/nginx/html

# إعداد Nginx
COPY nginx.conf /etc/nginx/conf.d/default.conf

# ── تشغيل non-root ──
# nginx:alpine فيه مستخدم 'nginx' (uid 101). نهيّئ المجلّدات لتعمل بلا root،
# ونستخدم منفذ 8080 (>1024 لا يحتاج صلاحيّات root).
RUN sed -i 's/listen 80;/listen 8080;/' /etc/nginx/conf.d/default.conf \
 && sed -i '/user  nginx;/d' /etc/nginx/nginx.conf \
 && sed -i 's#pid        /run/nginx.pid;#pid /tmp/nginx.pid;#' /etc/nginx/nginx.conf \
 && touch /tmp/nginx.pid \
 && chown -R nginx:nginx /usr/share/nginx/html /var/cache/nginx /tmp/nginx.pid \
 && chmod -R g+w /var/cache/nginx

USER nginx

# صحّة الحاوية — endpoint مخصّص (موثوق أكثر من grep على المحتوى)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -qO- http://127.0.0.1:8080/healthz || exit 1

EXPOSE 8080

CMD ["nginx", "-g", "daemon off;"]
