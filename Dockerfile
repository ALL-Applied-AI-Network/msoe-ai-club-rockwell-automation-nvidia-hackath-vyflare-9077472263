FROM node:24-bookworm-slim AS build
WORKDIR /app
RUN npm install --global pnpm@11.25.0
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY client/ client/
COPY server/ server/
COPY shared/ shared/
RUN pnpm run build

FROM node:24-bookworm-slim
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build /app/node_modules node_modules/
COPY --from=build /app/client/dist client/dist/
COPY --from=build /app/server/dist server/dist/
COPY package.json ./
COPY evidence/ evidence/
COPY backend/model4_assets/recipes.json backend/model4_assets/manifest.json backend/model4_assets/
COPY fluid-mixing-anomaly-detection/outputs/demo_data.json fluid-mixing-anomaly-detection/outputs/demo_data.json
COPY fluid-mixing-anomaly-detection/demo/thumbs/ fluid-mixing-anomaly-detection/demo/thumbs/
COPY cosmos-model-data/batch-results/20261025-batch01/summary.json cosmos-model-data/batch-results/20261025-batch01/summary.json
EXPOSE 8787
CMD ["node", "server/dist/server/src/index.js"]
