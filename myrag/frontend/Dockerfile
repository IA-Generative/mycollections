# Build stage — Nuxt 4 static generation (SSR disabled in nuxt.config.ts).
FROM node:22-alpine AS builder

WORKDIR /app

# Runtime config URLs are baked in at build time (ssr:false, no server).
# Override by rebuilding the image with different ARGs per environment.
ARG MYRAG_API_URL=/api
ARG KEYCLOAK_URL=https://mysso.fake-domain.name
ARG KEYCLOAK_REALM=openwebui
ARG KEYCLOAK_CLIENT_ID=myrag-front
ARG APP_TITLE="Mes collections (beta)"
ARG AUTH_ENABLED=true
ARG MYRAG_PUBLIC_URL=https://mycorpus.fake-domain.name

ENV MYRAG_API_URL=$MYRAG_API_URL \
    KEYCLOAK_URL=$KEYCLOAK_URL \
    KEYCLOAK_REALM=$KEYCLOAK_REALM \
    KEYCLOAK_CLIENT_ID=$KEYCLOAK_CLIENT_ID \
    APP_TITLE=$APP_TITLE \
    AUTH_ENABLED=$AUTH_ENABLED

COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund --prefer-offline

COPY . .
RUN npx nuxt generate


# Runtime stage — tiny nginx serving the static SPA with client-side routing fallback.
FROM nginx:1.27-alpine

RUN rm -rf /usr/share/nginx/html/* \
    && rm /etc/nginx/conf.d/default.conf

COPY --from=builder /app/.output/public /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=3s CMD wget -q -O /dev/null http://127.0.0.1:3000/ || exit 1
