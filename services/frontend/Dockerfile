FROM node:20-slim AS base

# tsconfig `@common/*` alias가 services/frontend 기준 `../../packages/common_schemas/typescript/src/*`이므로
# 이미지 안에서도 모노레포 디렉토리 구조를 보존해야 next build가 alias를 풀 수 있다.
WORKDIR /app/services/frontend

COPY services/frontend/package.json services/frontend/package-lock.json* ./
RUN npm ci

COPY packages/common_schemas/typescript /app/packages/common_schemas/typescript
COPY services/frontend .

# next.config.mjs rewrites destination이 ${process.env.API_PROXY_TARGET}을 빌드 시점에 평가해
# 결과 문자열을 inline한다 — 런타임 env로는 늦다. build ARG로 받아 ENV에 노출한다.
ARG API_PROXY_TARGET=http://localhost:8000
ENV API_PROXY_TARGET=$API_PROXY_TARGET

RUN npm run build

EXPOSE 3000

CMD ["npm", "start"]
