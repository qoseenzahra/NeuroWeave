FROM public.ecr.aws/docker/library/node:22-bookworm-slim@sha256:83f487e0a63425e5b4d146fb5e5be574bcbe1b7b843d3ebafdd95eaf7767a7e5 AS build

WORKDIR /app
ARG NEUROWEAVE_REVISION=development
ENV NEXT_PUBLIC_NEUROWEAVE_REVISION=${NEUROWEAVE_REVISION}
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend ./
ENV NEXT_PUBLIC_LOCALFLOW_API_URL=""
RUN npm run build

FROM public.ecr.aws/docker/library/node:22-bookworm-slim@sha256:83f487e0a63425e5b4d146fb5e5be574bcbe1b7b843d3ebafdd95eaf7767a7e5 AS runtime
ARG NEUROWEAVE_REVISION=development
LABEL org.opencontainers.image.revision=${NEUROWEAVE_REVISION}

ENV NODE_ENV=production
WORKDIR /app

COPY --from=build --chown=node:node /app /app

USER node
EXPOSE 3000

CMD ["node", "node_modules/vinext/dist/cli.js", "start", "--hostname", "0.0.0.0", "--port", "3000"]
