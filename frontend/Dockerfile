FROM node:22-alpine AS build
RUN corepack enable && corepack prepare pnpm@9.15.9 --activate
WORKDIR /app
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY . .
RUN pnpm run build

# Caddy with the netcup DNS module for Let's Encrypt DNS challenges. xcaddy downloads a few
# hundred Go modules; the Go proxy and checksum server sometimes drop a connection, so retry.
FROM caddy:2.11-builder-alpine AS caddy
RUN for attempt in 1 2 3; do \
      xcaddy build --with github.com/caddy-dns/netcup@v1.0.0 && exit 0; \
      echo "xcaddy build failed (attempt $attempt), retrying" >&2; sleep 20; \
    done; exit 1

FROM caddy:2.11-alpine
LABEL org.opencontainers.image.source=https://github.com/MaximilianRau04/Compass
COPY --from=caddy /usr/bin/caddy /usr/bin/caddy
COPY --from=build /app/dist /srv
