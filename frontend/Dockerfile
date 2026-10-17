FROM node:20-alpine AS build
RUN corepack enable && corepack prepare pnpm@9.15.9 --activate
WORKDIR /app
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY . .
RUN pnpm run build

# Caddy with the netcup DNS module for Let's Encrypt DNS challenges
FROM caddy:2.10-builder-alpine AS caddy
RUN xcaddy build --with github.com/caddy-dns/netcup@v1.0.0

FROM caddy:2.10-alpine
LABEL org.opencontainers.image.source=https://github.com/MaximilianRau04/Compass
COPY --from=caddy /usr/bin/caddy /usr/bin/caddy
COPY --from=build /app/dist /srv
