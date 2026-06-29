# ---- Stage 1: build the YouTube PO-token provider (Node) ----
# Defeats YouTube's "confirm you're not a bot" on flagged (datacenter) IPs.
FROM node:25-bookworm-slim AS potbuild
RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /src
RUN git clone --depth 1 https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git .
WORKDIR /src/server
RUN npm install && npx tsc

# ---- Stage 2: bot + provider runtime ----
FROM python:3.12-slim

# ffmpeg for audio/video; ca-certificates so the Node provider can reach Google.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Node runtime + the built provider server. node:25 and python:3.12-slim are both
# Debian bookworm, so the node binary copied here is ABI-compatible.
COPY --from=potbuild /usr/local/bin/node /usr/local/bin/node
COPY --from=potbuild /src/server/build /opt/bgutil/build
COPY --from=potbuild /src/server/node_modules /opt/bgutil/node_modules
COPY --from=potbuild /src/server/package.json /opt/bgutil/package.json

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# Runs the PO-token provider (127.0.0.1:4416) + the bot together.
ENTRYPOINT ["sh", "/app/docker-entrypoint.sh"]
