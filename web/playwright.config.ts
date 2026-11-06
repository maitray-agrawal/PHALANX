import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 45000,
  expect: {
    timeout: 10000,
  },
  fullyParallel: false,
  workers: 2,
  reporter: "list",
  use: {
    baseURL: "http://localhost:5173",
    trace: "on-first-retry",
    headless: true,
  },
  webServer: {
    command: "npm run dev",
    url: "http://localhost:5173",
    reuseExistingServer: true,
    timeout: 30000,
  },
  projects: [
    {
      name: "Chromium",
      use: {
        ...devices["Desktop Chrome"],
      },
    },
    {
      name: "WebKit",
      use: {
        ...devices["Desktop Safari"],
      },
    },
    {
      name: "Firefox",
      use: {
        ...devices["Desktop Firefox"],
      },
    },
    {
      name: "iPhone SE size",
      use: {
        ...devices["iPhone SE"],
      },
    },
    {
      name: "Pixel 7 size",
      use: {
        ...devices["Pixel 7"],
      },
    },
    {
      name: "iPad size",
      use: {
        ...devices["iPad Mini"],
      },
    },
  ],
});
