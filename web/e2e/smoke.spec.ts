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

  test("App Shell & Footer Invariant", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
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
    await page.setViewportSize({ width: 1280, height: 800 });
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
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto("/#approvals");

    await expect(page.getByRole("heading", { name: "Human Supervisor Step-Up Review Queue" })).toBeVisible();
    await expect(page.getByText("req_stepup_1001")).toBeVisible();

    // Test Inspect Diff
    const inspectBtn = page.getByRole("button", { name: /Inspect Diff/i });
    await expect(inspectBtn).toBeVisible();
    await inspectBtn.click();
    await expect(page.getByText("Cryptographic Lock Canonical Integrity")).toBeVisible();

    // Switch persona to AGENT via profile menu
    const profileBtn = page.locator(".profile-pill-trigger");
    await profileBtn.click();
    const agentOption = page.getByRole("menuitem", { name: /AGENT/i });
    await agentOption.click();

    // Verify warning banner and disabled buttons
    await expect(page.getByText(/Role Restriction:/i)).toBeVisible();
    const authorizeBtn = page.getByRole("button", { name: "Authorize Transaction" });
    await expect(authorizeBtn).toBeDisabled();
    const declineBtn = page.getByRole("button", { name: "Decline" });
    await expect(declineBtn).toBeDisabled();

    // Switch back to APPROVER
    await profileBtn.click();
    const approverOption = page.getByRole("menuitem", { name: /APPROVER/i });
    await approverOption.click();
    await expect(authorizeBtn).toBeEnabled();
  });

  test("Scene 3: Cryptographic Shield-Wall Ledger & Hash Chain Sequence", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto("/#activity");

    await expect(page.getByRole("heading", { name: "Cryptographic Shield-Wall Ledger" })).toBeVisible();
    await expect(page.getByText("Transaction Activity Journal")).toBeVisible();
    await expect(page.getByTestId("chain-strip")).toBeVisible();

    // Verify Chain button
    const verifyBtn = page.getByRole("button", { name: /Verify Chain/i });
    await expect(verifyBtn).toBeVisible();
    await verifyBtn.click();

    // Verify intact status banner
    await expect(page.locator(".integrity-status-bar.green")).toBeVisible();
  });

  test("Multi-Viewport Screenshots: 1280px Desktop, 768px Tablet, 375px Mobile", async ({ page }) => {
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
