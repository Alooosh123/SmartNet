import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  testMatch: "**/*.spec.js",
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  timeout: 90_000,
  expect: { timeout: 15_000 },
  reporter: [["list"], ["html", { outputFolder: "playwright-report", open: "never" }]],
  use: {
    baseURL: "http://127.0.0.1:5173",
    browserName: "chromium",
    headless: true,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  webServer: [
    {
      command: "python -c \"from pathlib import Path; Path('playwright.db').unlink(missing_ok=True)\" && python -m uvicorn app:app --host 127.0.0.1 --port 8000",
      cwd: "../backend",
      url: "http://127.0.0.1:8000/api/health/ready",
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      env: {
        ENVIRONMENT: "development",
        DATABASE_URL: "sqlite+aiosqlite:///./playwright.db",
        SECRET_KEY: "smartnet-playwright-secret-key-2026-strong",
        PAYMENT_WEBHOOK_SECRET: "smartnet-playwright-webhook-secret-2026",
        DASHBOARD_USERNAME: "e2e-admin",
        DASHBOARD_PASSWORD: "SmartNet-E2E-admin-password-2026!",
        PAYMENT_PROVIDER_MODE: "manual",
        PAYMENT_DEMO_MODE: "false",
        MIKROTIK_DEMO_MODE: "true",
        OPENAI_API_KEY: "",
        CORS_ORIGINS: "[\"http://127.0.0.1:5173\"]",
      },
    },
    {
      command: "npm run dev -- --host 127.0.0.1",
      url: "http://127.0.0.1:5173",
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      env: { VITE_API_BASE_URL: "http://127.0.0.1:8000" },
    },
  ],
});
