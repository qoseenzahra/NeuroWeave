FROM public.ecr.aws/docker/library/node:22-bookworm-slim AS build

WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend ./
ENV NEXT_PUBLIC_LOCALFLOW_API_URL=""
RUN npm run build

FROM public.ecr.aws/docker/library/node:22-bookworm-slim AS runtime

ENV NODE_ENV=production
WORKDIR /app

COPY --from=build --chown=node:node /app /app

USER node
EXPOSE 3000

CMD ["node", "node_modules/vinext/dist/cli.js", "start", "--hostname", "0.0.0.0", "--port", "3000"]
