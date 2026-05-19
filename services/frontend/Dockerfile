FROM node:20-slim AS base

WORKDIR /app

COPY services/frontend/package.json services/frontend/package-lock.json* ./
RUN npm ci

COPY packages/common_schemas/typescript /app/packages/common_schemas/typescript
COPY services/frontend .

RUN npm run build

EXPOSE 3000

CMD ["npm", "start"]
