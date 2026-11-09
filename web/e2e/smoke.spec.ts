import { test, expect } from "@playwright/test";
import path from "node:path";
import fs from "node:fs";

const ARTIFACT_DIR = "C:/Users/agraw/.gemini/antigravity/brain/4e726a7c-0329-46ca-a4e5-63b031a277d0";
const LOCAL_SCREENSHOTS_DIR = path.resolve(process.cwd(), "screenshots");

test.describe("PHALANX PayPal-Inspired Shell & Operational Screens", () => {
  test.beforeAll(() => {
    if (!fs.existsSync(LOCAL_SCREENSHOTS_DIR)) {
      fs.mkdirSync(LOCAL_SCREENSHOTS_DIR, { recursive: true });
    }
    if (!fs.existsSync(ARTIFACT_DIR)) {
      fs.mkdirSync(ARTIFACT_DIR, { recursive: true });
    }
  });

  const cspViolations: string[] = [];

  test.beforeEach(async ({ page }, testInfo) => {
    // Monitor securitypolicyviolation events to verify strict CSP compliance
    page.on("securitypolicyviolation", (evt) => {
      cspViolations.push(`${evt.blockedURI} violated directive ${evt.violatedDirective}`);
    });

    // Throttle to slow 4G in Chromium project
    if (testInfo.project.name.toLowerCase().includes("chromium")) {
      try {
        const client = await page.context().newCDPSession(page);
        await client.send("Network.emulateNetworkConditions", {
          offline: false,
          downloadThroughput: (1.6 * 1024 * 1024) / 8, // 1.6 Mb/s Slow 4G profile
          uploadThroughput: (750 * 1024) / 8, // 750 kb/s
          latency: 150, // 150 ms RTT
        });
      } catch {
        // Fallback for non-CDP engines
      }
    }
  });

  test.afterEach(async () => {
    expect(cspViolations, `CSP violations detected: ${cspViolations.join(", ")}`).toHaveLength(0);
    cspViolations.length = 0;
  });

  async function setPersona(page: import("@playwright/test").Page, role: "APPROVER" | "AGENT" | "PRINCIPAL" | "AUDITOR") {
    const profileTrigger = page.locator(".profile-pill-trigger");
    if (await profileTrigger.isVisible()) {
      await profileTrigger.click();
      const menuitem = page.getByRole("menuitem", { name: new RegExp(role, "i") });
      await menuitem.click();
    } else {
      const moreBtn = page.locator('.mobile-bottom-tabbar button[aria-label="More"]');
      if (await moreBtn.isVisible()) {
        await moreBtn.click();
        const personaBtn = page.locator(`.mobile-more-sheet .persona-grid button:has-text("${role}")`);
        await personaBtn.click();
      }
    }
  }

  test("App Shell & Footer Invariant", async ({ page }) => {
    test.slow();
    await page.goto("/#home");

    // Brand wordmark and sandbox indicator
    await expect(page.locator(".brand-wordmark")).toHaveText("PHALANX");
    await expect(page.locator(".sandbox-indicator")).toHaveText("SANDBOX");

    // Mandatory disclaimer
    await expect(page.locator(".footer-disclaimer")).toHaveText("Not affiliated with PayPal.");

    // Home screen numbers
    await expect(page.getByText("REMAINING AUTHORITY")).toBeVisible();
    await expect(page.getByText("PENDING APPROVALS")).toBeVisible();
    await expect(page.getByText("LAST RECORDED ACTIVITY")).toBeVisible();
  });

  test("Scene 1: Pay / Request Console with Intent Card & Instant Decision", async ({ page }) => {
    await page.goto("/#pay");

    await expect(page.getByRole("heading", { name: "Propose Financial Transaction" })).toBeVisible();

    // Presets exist
    const presetAllow = page.getByText("Under Limit ($25 - ALLOW)");
    await expect(presetAllow).toBeVisible();
    await presetAllow.click();

    // Verify input fields populated by preset
    await expect(page.locator("input#recipient-id")).toHaveValue("vendor-paypal-sandbox-1");
    await expect(page.locator("input#amount")).toHaveValue("25.00");

    // Trigger evaluation
    const submitBtn = page.getByRole("button", { name: "Evaluate & Submit Intent to Policy Core" });
    await expect(submitBtn).toBeVisible();
    await submitBtn.click();

    // Decision badge and intent card render after evaluation
    await expect(page.getByTestId("decision-badge").first()).toBeVisible();
    await expect(page.getByTestId("request-card")).toBeVisible();
    await expect(page.getByText("APPLIED POLICY REASONS")).toBeVisible();
  });

  test("Scene 2: Human Supervisor Step-Up Review Queue & Digest Binding", async ({ page }) => {
    await page.goto("/#approvals");

    await expect(page.getByRole("heading", { name: "Human Supervisor Step-Up Review Queue" })).toBeVisible();
    await expect(page.getByText("req_stepup_1001")).toBeVisible();

    // Test Inspect Diff
    const inspectBtn = page.getByRole("button", { name: /Inspect Diff/i }).first();
    await expect(inspectBtn).toBeVisible();
    await inspectBtn.click();
    await expect(page.getByText("Cryptographic Lock Canonical Integrity")).toBeVisible();

    // Switch persona to AGENT via profile menu / sheet
    await setPersona(page, "AGENT");

    // Verify warning banner and disabled buttons
    await expect(page.getByText(/Role Restriction:/i)).toBeVisible();
    const authorizeBtn = page.getByRole("button", { name: "Authorize Transaction" }).first();
    await expect(authorizeBtn).toBeDisabled();
    const declineBtn = page.getByRole("button", { name: "Decline" }).first();
    await expect(declineBtn).toBeDisabled();

    // Switch back to APPROVER
    await setPersona(page, "APPROVER");
    await expect(authorizeBtn).toBeEnabled();
  });

  test("Scene 3: Cryptographic Shield-Wall Ledger & Hash Chain Sequence", async ({ page }) => {
    await page.goto("/#activity");
    await setPersona(page, "APPROVER");

    await expect(page.getByRole("heading", { name: "Cryptographic Shield-Wall Ledger" })).toBeVisible();
    await expect(page.getByText("Transaction Activity Journal")).toBeVisible();
    await expect(page.getByTestId("chain-strip")).toBeVisible({ timeout: 20000 });

    // Verify Chain button
    const verifyBtn = page.getByRole("button", { name: /Verify Chain/i });
    await expect(verifyBtn).toBeVisible();
    await verifyBtn.click();

    // Verify intact status banner
    await expect(page.locator(".integrity-status-bar.green")).toBeVisible({ timeout: 20000 });
  });

  test("Multi-Viewport Screenshots: 1280px Desktop, 768px Tablet, 375px Mobile", async ({ page }) => {
    test.slow();
    // 1. Desktop Viewport (1280 x 800)
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto("/#home");
    await page.waitForLoadState("networkidle");
    const desktopPath = path.join(LOCAL_SCREENSHOTS_DIR, "screenshot-1280-desktop.png");
    const artifactDesktop = path.join(ARTIFACT_DIR, "screenshot-1280-desktop.png");
    await page.screenshot({ path: desktopPath, fullPage: true });
    try {
      fs.copyFileSync(desktopPath, artifactDesktop);
    } catch {
      // Artifact dir copy fallback
    }

    // 2. Tablet Viewport (768 x 1024)
    await page.setViewportSize({ width: 768, height: 1024 });
    await page.goto("/#home");
    await page.waitForLoadState("networkidle");
    const tabletPath = path.join(LOCAL_SCREENSHOTS_DIR, "screenshot-768-tablet.png");
    const artifactTablet = path.join(ARTIFACT_DIR, "screenshot-768-tablet.png");
    await page.screenshot({ path: tabletPath, fullPage: true });
    try {
      fs.copyFileSync(tabletPath, artifactTablet);
    } catch {
      // Artifact dir copy fallback
    }

    // 3. Mobile Viewport (375 x 667 - iPhone SE/8)
    await page.setViewportSize({ width: 375, height: 667 });
    await page.goto("/#home");
    await page.waitForLoadState("networkidle");

    // Check sticky action bar and bottom tab bar on mobile
    await expect(page.locator(".mobile-bottom-tabbar")).toBeVisible();
    await expect(page.locator(".mobile-sticky-action-bar")).toBeVisible();

    // Verify no horizontal overflow at 375px
    const hasHorizontalOverflow = await page.evaluate(() => {
      return document.documentElement.scrollWidth > document.documentElement.clientWidth;
    });
    expect(hasHorizontalOverflow).toBe(false);

    const mobilePath = path.join(LOCAL_SCREENSHOTS_DIR, "screenshot-375-mobile.png");
    const artifactMobile = path.join(ARTIFACT_DIR, "screenshot-375-mobile.png");
    await page.screenshot({ path: mobilePath, fullPage: true });
    try {
      fs.copyFileSync(mobilePath, artifactMobile);
    } catch {
      // Artifact dir copy fallback
    }
  });
});
