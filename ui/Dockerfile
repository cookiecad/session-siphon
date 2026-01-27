# syntax=docker/dockerfile:1

# Stage 1: Dependencies
FROM node:20-alpine AS deps

WORKDIR /app

# Install dependencies based on the preferred package manager
COPY package.json package-lock.json* yarn.lock* pnpm-lock.yaml* ./

RUN \
    if [ -f yarn.lock ]; then yarn install --frozen-lockfile; \
    elif [ -f package-lock.json ]; then npm ci; \
    elif [ -f pnpm-lock.yaml ]; then corepack enable pnpm && pnpm install --frozen-lockfile; \
    else npm install; \
    fi

# Stage 2: Build
FROM node:20-alpine AS builder

WORKDIR /app

# Copy dependencies from deps stage
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# Accept build-time environment variables for Typesense config
ARG NEXT_PUBLIC_TYPESENSE_HOST=localhost
ARG NEXT_PUBLIC_TYPESENSE_PORT=8108
ARG NEXT_PUBLIC_TYPESENSE_PROTOCOL=http
ARG NEXT_PUBLIC_TYPESENSE_API_KEY=dev-api-key

ENV NEXT_PUBLIC_TYPESENSE_HOST=$NEXT_PUBLIC_TYPESENSE_HOST
ENV NEXT_PUBLIC_TYPESENSE_PORT=$NEXT_PUBLIC_TYPESENSE_PORT
ENV NEXT_PUBLIC_TYPESENSE_PROTOCOL=$NEXT_PUBLIC_TYPESENSE_PROTOCOL
ENV NEXT_PUBLIC_TYPESENSE_API_KEY=$NEXT_PUBLIC_TYPESENSE_API_KEY

# Set Next.js to output standalone mode
ENV NEXT_TELEMETRY_DISABLED=1

# Build the application
RUN npm run build

# Stage 3: Production
FROM node:20-alpine AS runner

WORKDIR /app

# Set production environment
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

# Create non-root user
RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs

# Copy built assets from builder
COPY --from=builder /app/public ./public

# Set correct permissions for prerender cache
RUN mkdir -p .next && chown nextjs:nodejs .next

# Copy standalone build
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

# Switch to non-root user
USER nextjs

# Expose port
EXPOSE 3000

ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

# Run the application
CMD ["node", "server.js"]
