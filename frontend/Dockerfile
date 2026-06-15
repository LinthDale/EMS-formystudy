# =============================================================================
# EMS 前端 production image（PRD-0005 §9.5 / security review M-1）
# 多階段：node build（Vite static build）→ nginx serve（靜態 + §9.5 標頭 + /api 代理）
# dev 模式仍走 docker-compose 的 node:24-alpine + `vite dev`（profiles: ["dev"]）；
# 本 Dockerfile 專供 prod 靜態服務，不含任何金鑰（SPA bundle 公開可下載，§9.1）。
# =============================================================================

# ── Stage 1: build ───────────────────────────────────────────────────────────
# 與 dev compose 一致的 node 主版本（node:24-alpine），確保 build 與 dev 行為一致。
FROM node:24-alpine AS build
WORKDIR /app

# 先只拷 manifest → 善用 layer cache（依賴未變時不重裝）。
# 用 npm ci：依 package-lock.json 可重現安裝（含 devDeps，build 需 vite/tsc）。
COPY package.json package-lock.json ./
RUN npm ci

# 拷其餘原始碼並產出靜態 build（tsc -b && vite build → dist/）
COPY . .
RUN npm run build

# ── Stage 2: serve ─────────────────────────────────────────────────────────────
# nginx alpine：只帶靜態 dist + 我們的 nginx.conf；不含 node / 原始碼 / 金鑰。
FROM nginx:1.27-alpine AS serve

# 換掉預設 server 區塊：注入 §9.5 安全標頭 + SPA fallback + /api → BFF 代理
RUN rm -f /etc/nginx/conf.d/default.conf
COPY nginx.conf /etc/nginx/conf.d/ems-frontend.conf

# 只搬 build 產物（不帶 node_modules / 原始碼）
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

# 容器層健康檢查（對齊 nginx.conf 的 /healthz；orchestrator 探活）
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD wget -qO- http://127.0.0.1/healthz >/dev/null 2>&1 || exit 1

CMD ["nginx", "-g", "daemon off;"]
