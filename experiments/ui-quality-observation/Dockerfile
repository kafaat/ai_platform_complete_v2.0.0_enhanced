# Impeccable v4.8.0 static source detector. No SAHOOL frontend built or run.
FROM node:24-bookworm-slim
ENV npm_config_ignore_scripts=true npm_config_audit=false npm_config_fund=false
WORKDIR /opt/impeccable
RUN npm init -y >/dev/null && npm install --ignore-scripts --no-audit --no-fund --omit=dev --include=optional --save-exact impeccable@4.8.0
RUN mkdir -p /work && chmod 755 /work
ENV PATH="/opt/impeccable/node_modules/.bin:$PATH"
USER node
ENTRYPOINT ["impeccable"]
