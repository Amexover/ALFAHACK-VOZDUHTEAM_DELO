import { defineConfig } from "@playwright/test";
import { existsSync } from "node:fs";
import { resolve } from "node:path";

const localPython = resolve(
  "../backend/.venv",
  process.platform === "win32" ? "Scripts/python.exe" : "bin/python",
);
const python =
  process.env.DELO_TEST_PYTHON ||
  (existsSync(localPython) ? localPython : "python");
export default defineConfig({
  testDir: "./tests",
  testMatch: "**/*.spec.ts",
  fullyParallel: false,
  workers: 1,
  timeout: 35_000,
  expect: { timeout: 10_000 },
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:5177",
    viewport: { width: 1440, height: 1000 },
    browserName: "chromium",
    launchOptions: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE
      ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE }
      : {},
    trace: "retain-on-failure",
  },
  webServer: [
    {
      command: `"${python}" tests/serve_backend.py`,
      url: "http://127.0.0.1:8017/api/health",
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      command: "npm run dev -- --port 5177 --strictPort",
      env: { DELO_API_TARGET: "http://127.0.0.1:8017" },
      url: "http://127.0.0.1:5177",
      reuseExistingServer: false,
      timeout: 60_000,
    },
  ],
});
