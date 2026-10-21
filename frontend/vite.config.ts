import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { "/api": { target: "http://195.133.41.30", changeOrigin: true } },
  },
  build: { sourcemap: false },
});
