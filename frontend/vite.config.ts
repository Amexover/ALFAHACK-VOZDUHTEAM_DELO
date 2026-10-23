import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { fileURLToPath } from "node:url";
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  server: {
    proxy: {
      "/api": {
        target: process.env.DELO_API_TARGET || "http://127.0.0.1:8010",
        changeOrigin: true,
        configure(proxy) {
          // Propagate a cancelled SSE reader to FastAPI during local development.
          proxy.on("proxyReq", (proxyReq, _req, res) => {
            res.on("close", () => {
              if (!res.writableEnded) proxyReq.destroy();
            });
          });
        },
      },
    },
  },
  build: {
    sourcemap: false,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (
            id.includes("node_modules") &&
            /[\\/](motion|motion-dom|motion-utils|framer-motion)[\\/]/.test(id)
          )
            return "agent-motion";
        },
      },
    },
  },
});
