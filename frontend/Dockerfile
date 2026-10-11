FROM node:24-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

FROM node:24-alpine AS build
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ARG API_INTERNAL_URL=http://api:8000
ENV API_INTERNAL_URL=$API_INTERNAL_URL
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:24-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT=3000
ENV HOSTNAME=0.0.0.0
RUN addgroup --system --gid 1001 paxveil && adduser --system --uid 1001 --ingroup paxveil paxveil
COPY --from=build --chown=paxveil:paxveil /app/.next/standalone ./
COPY --from=build --chown=paxveil:paxveil /app/.next/static ./.next/static
COPY --from=build --chown=paxveil:paxveil /app/public ./public
USER paxveil
EXPOSE 3000
CMD ["node", "server.js"]
