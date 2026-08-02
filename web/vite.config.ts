import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "VITE_");
  const useApi = env.VITE_COUPFE_BACKEND === "fastapi";

  return {
    base: env.VITE_BASE_PATH || "./",
    plugins: [react()],
    server: {
      proxy: useApi
        ? {
            "/api": {
              target: env.VITE_COUPFE_API_DEV_TARGET || "http://127.0.0.1:8000",
              changeOrigin: false,
            },
          }
        : undefined,
    },
    test: {
      environment: "jsdom",
      setupFiles: "./src/test/setup.ts",
      css: true,
      restoreMocks: true,
    },
  };
});
