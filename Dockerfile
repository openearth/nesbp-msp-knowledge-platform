# NESBp MSP knowledge-sharing platform
# Multi-stage: build Quarto site, then serve static files with nginx.
#
# EDITO (add-your-service → Deploy from a Dockerfile):
#   - Dockerfile path: Dockerfile
#   - Network / Port: 8080

# ---- Build: Quarto + Python (pre-render) ----
FROM debian:bookworm-slim AS builder

ARG QUARTO_VERSION=1.7.32

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        python3 \
    && curl -fsSL -o /tmp/quarto.deb \
        "https://github.com/quarto-dev/quarto-cli/releases/download/v${QUARTO_VERSION}/quarto-${QUARTO_VERSION}-linux-amd64.deb" \
    && dpkg -i /tmp/quarto.deb \
    && rm -f /tmp/quarto.deb \
    && ln -sf /usr/bin/python3 /usr/bin/python \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy only what Quarto needs to render (see .dockerignore)
COPY . .

RUN quarto render

# ---- Runtime: static file server ----
FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/_site /usr/share/nginx/html

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget -qO- http://127.0.0.1:8080/ >/dev/null || exit 1

CMD ["nginx", "-g", "daemon off;"]
