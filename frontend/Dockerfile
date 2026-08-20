FROM node:22.14-slim AS build

ARG APP_VERSION=2.0.7

WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/index.html ./index.html
COPY frontend/vite.config.js ./vite.config.js
COPY frontend/src/ ./src/
RUN npm run build

FROM nginxinc/nginx-unprivileged:alpine@sha256:a6c3ec0c0d249d68b0682df854d4a9e222b90fb607dc3fcf2f1d2fcbc85d347e AS runtime

ARG APP_VERSION=2.0.7

LABEL org.opencontainers.image.title="Personal Job Agent Frontend" \
      org.opencontainers.image.version="${APP_VERSION}"

COPY frontend/nginx.conf /etc/nginx/nginx.conf
COPY --from=build /app/dist/ /usr/share/nginx/html/

USER 101:101
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD ["wget", "--quiet", "--tries=1", "--spider", "http://127.0.0.1:8080/healthz"]
