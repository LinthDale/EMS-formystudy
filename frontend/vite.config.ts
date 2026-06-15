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
    },
  },
});
