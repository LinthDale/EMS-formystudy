import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// PRD-0005 §6.4 / §9.3 — SPA 一律經同源 BFF（/api）取數；dev 模式 proxy 到本機 BFF。
// BFF（FastAPI, services/bff，:8003）已交付；compose 綁 127.0.0.1:8003。此 proxy 僅 dev 佈線，無金鑰。
const BFF_DEV_TARGET = "http://localhost:8003";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  server: {
    proxy: {
      "/api": { target: BFF_DEV_TARGET, changeOrigin: true },
    },
  },
  build: {
    rollupOptions: {
      output: {
        // 圖表 / framework 各自成 chunk：app shell 輕量化（NFR LCP < 2.5s）
        manualChunks: {
          echarts: ["echarts/core", "echarts/charts", "echarts/components", "echarts/renderers"],
          react: ["react", "react-dom"],
        },
      },
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: false,
    coverage: {
      provider: "v8",
      include: ["src/**"],
      exclude: [
        "src/main.tsx",
        "src/api/schema.ts",
        "src/test/**",
        "src/**/__tests__/**",
        "src/vite-env.d.ts",
      ],
      // 覆蓋率下限（code review MED）：對齊 project_rules.md §10「FastAPI endpoint 80%」精神，
      // 前端 line/statement/branch 同採 80% 為硬下限，CI 在 frontend-unit job 跑 `npm run coverage` 強制。
      //
      // functions 刻意「不」設 80%：src/api/client.ts 的 mutating 樁方法
      // （createDevice/updateDevice/confirm/override/reject…）在 P1 僅以 EmsApiNotWiredError 佔位，
      // 要等 BFF 實際接線（§8.2「BFF 對外 facade 屬本 PRD 實作面」）才會被測試行使，
      // 故全專案 functions ≈ 74%。設一個務實下限 70% 防回歸，待 live wiring 後再升至 80%。
      thresholds: {
        lines: 80,
        statements: 80,
        branches: 80,
        functions: 70,
      },
    },
  },
});
