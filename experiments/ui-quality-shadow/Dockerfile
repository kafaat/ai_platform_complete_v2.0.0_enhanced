# Offline static TSX source survey only; never runs the SAHOOL UI or a browser.
FROM node:24-bookworm-slim@sha256:c86ecead9e55a5210ac1727de38a4ca840bf03dcaf34dc9749addbf383b1920c
ENV npm_config_ignore_scripts=true npm_config_audit=false npm_config_fund=false
WORKDIR /opt/impeccable
RUN npm init -y >/dev/null && npm install --ignore-scripts --no-audit --no-fund --omit=dev --include=optional --save-exact impeccable@4.8.0
RUN mkdir -p /scan && chmod 0755 /scan
ENV PATH="/opt/impeccable/node_modules/.bin:$PATH"
USER node
ENTRYPOINT ["impeccable"]
