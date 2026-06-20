FROM node:20-alpine AS build
WORKDIR /app
COPY src/package.json src/package-lock.json* ./
RUN npm install --legacy-peer-deps --ignore-scripts
COPY src/ .
ARG API_BASE=http://localhost:8100
ENV NUXT_PUBLIC_API_BASE=$API_BASE
RUN npm run build

FROM node:20-alpine
WORKDIR /app
COPY --from=build /app/.output ./
EXPOSE 3000
CMD ["node", "server/index.mjs"]
