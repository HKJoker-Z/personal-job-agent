import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(() => {
  const proxyTarget = process.env.VITE_BACKEND_PROXY_TARGET;
  return {
    plugins: [react()],
    server: {
      host: "0.0.0.0",
      allowedHosts: true,
      proxy: proxyTarget
        ? { "/api": { target: proxyTarget, changeOrigin: true } }
        : undefined,
    },
    test: {
      environment: "jsdom",
      setupFiles: "./src/test-setup.js",
      clearMocks: true,
      globals: true,
    },
  };
});
