FROM node:20-bookworm-slim AS dependencies
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:20-bookworm-slim AS builder
WORKDIR /app
ARG NEXT_PUBLIC_API_URL
ARG NEXT_PUBLIC_SUPABASE_URL
ARG NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY
ARG NEXT_PUBLIC_SUPABASE_ANON_KEY
ARG NEXT_PUBLIC_MAX_FILE_SIZE_MB=10
ARG NEXT_PUBLIC_MAX_FILES_PER_REQUEST=50
ARG NEXT_PUBLIC_MAX_BATCH_SIZE_MB=100
ENV NEXT_TELEMETRY_DISABLED=1 \
    NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL} \
    NEXT_PUBLIC_SUPABASE_URL=${NEXT_PUBLIC_SUPABASE_URL} \
    NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=${NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY} \
    NEXT_PUBLIC_SUPABASE_ANON_KEY=${NEXT_PUBLIC_SUPABASE_ANON_KEY} \
    NEXT_PUBLIC_MAX_FILE_SIZE_MB=${NEXT_PUBLIC_MAX_FILE_SIZE_MB} \
    NEXT_PUBLIC_MAX_FILES_PER_REQUEST=${NEXT_PUBLIC_MAX_FILES_PER_REQUEST} \
    NEXT_PUBLIC_MAX_BATCH_SIZE_MB=${NEXT_PUBLIC_MAX_BATCH_SIZE_MB}
COPY --from=dependencies /app/node_modules ./node_modules
COPY . ./
RUN npm run build

FROM node:20-bookworm-slim AS runtime
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0
RUN addgroup --system --gid 1001 nodejs \
    && adduser --system --uid 1001 --ingroup nodejs nextjs
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
USER nextjs
EXPOSE 3000
CMD ["node", "server.js"]
