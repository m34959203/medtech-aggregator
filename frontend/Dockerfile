# Node 24 — соответствует версии, сгенерировавшей package-lock (иначе npm ci падает).
FROM node:24-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:24-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# Публичный origin вшивается в клиентский бандл на build (NEXT_PUBLIC_*).
ARG NEXT_PUBLIC_API_URL=https://medtech.technokod.kz
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV INTERNAL_API_URL=http://medtech-backend:8000
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:24-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT=3000
ENV HOSTNAME=0.0.0.0
# INTERNAL_API_URL читается в rewrites() при старте сервера (проксирование /api).
ENV INTERNAL_API_URL=http://medtech-backend:8000
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
EXPOSE 3000
CMD ["node", "server.js"]
