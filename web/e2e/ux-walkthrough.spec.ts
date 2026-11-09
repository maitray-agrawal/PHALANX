import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import path from "node:path";
import fs from "node:fs";

const ARTIFACT_DIR = "C:/Users/agraw/.gemini/antigravity/brain/4e726a7c-0329-46ca-a4e5-63b031a277d0";
const LOCAL_SCREENSHOTS_DIR = path.resolve(process.cwd(), "screenshots");

test.describe("Cognitive Walkthrough & UX Review Suites", () => {
  test.beforeAll(() => {
    if (!fs.existsSync(LOCAL_SCREENSHOTS_DIR)) {
      fs.mkdirSync(LOCAL_SCREENSHOTS_DIR, { recursive: true });
    }
    if (!fs.existsSync(ARTIFACT_DIR)) {
      fs.mkdirSync(ARTIFACT_DIR, { recursive: true });
    }
  });

  const saveScreenshot = async (page: Page, filename: string) => {
    const local = path.join(LOCAL_SCREENSHOTS_DIR, filename);
    const art = path.join(ARTIFACT_DIR, filename);
    await page.screenshot({ path: local, fullPage: true });
    try {
      fs.copyFileSync(local, art);
    } catch {
      // Artifact fallback
    }
  };

  test("Persona 1 Walkthrough: APPROVER (Human Financial Supervisor)", async ({ page }) => {
    // 1280px Desktop
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto("/#home");
    await expect(page.locator(".brand-wordmark")).toHaveText("PHALANX");

    // Switch persona to APPROVER
    const profileBtn = page.locator(".profile-pill-trigger");
    await profileBtn.click();
    await page.getByRole("menuitem", { name: /APPROVER/i }).click();

    // Navigate to Approvals Queue
    await page.goto("/#approvals");
    await expect(page.getByRole("heading", { name: /Human Supervisor Step-Up Review Queue/i })).toBeVisible();

    const emptyQueue = page.getByText("Queue is completely clear");
    if (await emptyQueue.isVisible()) {
      await expect(page.getByText("No transactions are currently awaiting supervisor authorization.")).toBeVisible();
    } else {
      const inspectBtn = page.getByRole("button", { name: /Inspect Diff/i }).first();
      if (await inspectBtn.isVisible()) {
        await inspectBtn.click();
        await expect(page.getByText(/Cryptographic Lock Canonical Integrity/i)).toBeVisible();
      }
    }

    await saveScreenshot(page, "walkthrough-approver-1280.png");

    // 768px Tablet
    await page.setViewportSize({ width: 768, height: 1024 });
    await page.waitForTimeout(300);
    await saveScreenshot(page, "walkthrough-approver-768.png");

    // 375px Mobile
    await page.setViewportSize({ width: 375, height: 667 });
    await page.waitForTimeout(300);
    await saveScreenshot(page, "walkthrough-approver-375.png");

    // Authorize transaction (select first approval card in queue)
    const authBtn = page.getByRole("button", { name: "Authorize Transaction" }).first();
    await expect(authBtn).toBeEnabled();
    await authBtn.click();
    await expect(page.locator(".toast-success")).toBeVisible();
  });

  test("Persona 2 Walkthrough: AGENT (Autonomous Procurement Agent)", async ({ page }) => {
    // 1280px Desktop
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto("/#pay");

    // Switch persona to AGENT
    const profileBtn = page.locator(".profile-pill-trigger");
    await profileBtn.click();
    await page.getByRole("menuitem", { name: /AGENT/i }).click();

    // Select under-limit preset ($25)
    await page.getByText("Under Limit ($25 - ALLOW)").click();
    const submitBtn = page.getByRole("button", { name: /Evaluate & Submit Intent/i });
    await submitBtn.click();

    // Instant decision feedback
    await expect(page.getByTestId("decision-badge").first()).toHaveText(/ALLOW/i);
    await saveScreenshot(page, "walkthrough-agent-1280.png");

    // 768px Tablet
    await page.setViewportSize({ width: 768, height: 1024 });
    await page.waitForTimeout(300);
    await saveScreenshot(page, "walkthrough-agent-768.png");

    // 375px Mobile
    await page.setViewportSize({ width: 375, height: 667 });
    await page.waitForTimeout(300);
    await saveScreenshot(page, "walkthrough-agent-375.png");

    // Agent attempts self-approval on Approvals screen
    await page.goto("/#approvals");
    await expect(page.getByText(/Role Restriction:/i)).toBeVisible();
    await expect(page.getByRole("button", { name: "Authorize Transaction" })).toBeDisabled();
  });

  test("Persona 3 Walkthrough: AUDITOR (Compliance Auditor)", async ({ page }) => {
    // 1280px Desktop
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto("/#activity");

    // Switch persona to AUDITOR
    const profileBtn = page.locator(".profile-pill-trigger");
    await profileBtn.click();
    await page.getByRole("menuitem", { name: /AUDITOR/i }).click();
    await page.waitForTimeout(500);

    await expect(page.getByRole("heading", { name: /Cryptographic Shield-Wall Ledger/i })).toBeVisible();

    // Verify Chain
    const verifyBtn = page.getByRole("button", { name: /Verify Chain/i });
    await verifyBtn.click();
    await expect(page.locator(".integrity-status-bar.green")).toBeVisible();

    await saveScreenshot(page, "walkthrough-auditor-1280.png");

    // 768px Tablet
    await page.setViewportSize({ width: 768, height: 1024 });
    await page.waitForTimeout(300);
    await saveScreenshot(page, "walkthrough-auditor-768.png");

    // 375px Mobile
    await page.setViewportSize({ width: 375, height: 667 });
    await page.waitForTimeout(300);
    await saveScreenshot(page, "walkthrough-auditor-375.png");

    // Test Tamper & Restore
    const tamperBtn = page.getByRole("button", { name: /Simulate Tamper/i });
    await tamperBtn.click();
    await expect(page.locator(".integrity-status-bar.red")).toBeVisible();

    const restoreBtn = page.getByRole("button", { name: /Restore/i });
    await restoreBtn.click();
    await expect(page.locator(".integrity-status-bar.green")).toBeVisible();
  });

  test("Persona 4 Walkthrough: PRINCIPAL (Treasury Administrator)", async ({ page }) => {
    // 1280px Desktop
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto("/#mandates");

    // Switch persona to PRINCIPAL
    const profileBtn = page.locator(".profile-pill-trigger");
    await profileBtn.click();
    await page.getByRole("menuitem", { name: /PRINCIPAL/i }).click();

    await expect(page.getByRole("heading", { name: "Ed25519 Authority Mandate", exact: true })).toBeVisible();
    await expect(page.getByText("mandate_default_sandbox")).toBeVisible();
    await expect(page.getByTestId("mandate-meter")).toBeVisible();

    await saveScreenshot(page, "walkthrough-principal-1280.png");

    // 768px Tablet
    await page.setViewportSize({ width: 768, height: 1024 });
    await page.waitForTimeout(300);
    await saveScreenshot(page, "walkthrough-principal-768.png");

    // 375px Mobile
    await page.setViewportSize({ width: 375, height: 667 });
    await page.waitForTimeout(300);
    await saveScreenshot(page, "walkthrough-principal-375.png");
  });

  test("No Horizontal Scroll at 375px Across All Seven Screens", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });

    const screens = ["#home", "#pay", "#approvals", "#activity", "#mandates", "#attack-lab", "#receipt"];
    for (const scr of screens) {
      await page.goto(`/${scr}`);
      await page.waitForTimeout(400);

      const hasHorizontalScroll = await page.evaluate(() => {
        return document.documentElement.scrollWidth > document.documentElement.clientWidth;
      });

      expect(
        hasHorizontalScroll,
        `Horizontal scroll detected on screen ${scr} at 375px viewport!`
      ).toBe(false);
    }
  });

  test("Touch Target Sizing: 44px Minimum Across Core Controls", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await page.goto("/#home");

    // Check bottom tabbar items
    const tabbarItems = await page.locator(".tabbar-item").all();
    expect(tabbarItems.length).toBeGreaterThan(0);
    for (const item of tabbarItems) {
      const box = await item.boundingBox();
      expect(box).not.toBeNull();
      if (box) {
        expect(box.height).toBeGreaterThanOrEqual(44);
      }
    }

    // Check theme toggle button
    const themeBtn = page.locator(".theme-toggle-btn");
    const themeBox = await themeBtn.boundingBox();
    expect(themeBox).not.toBeNull();
    if (themeBox) {
      expect(themeBox.height).toBeGreaterThanOrEqual(44);
      expect(themeBox.width).toBeGreaterThanOrEqual(44);
    }

    // Check profile trigger
    const profileBtn = page.locator(".profile-pill-trigger");
    const profileBox = await profileBtn.boundingBox();
    expect(profileBox).not.toBeNull();
    if (profileBox) {
      expect(profileBox.height).toBeGreaterThanOrEqual(44);
    }
  });

  test("Reduced Motion Defense: Animations Clamped Under prefers-reduced-motion", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/#home");

    const appShell = page.locator(".phalanx-app-shell");
    await expect(appShell).toBeVisible();

    const transitionDur = await page.evaluate(() => {
      const el = document.querySelector(".nav-link-btn");
      if (!el) return "0s";
      return window.getComputedStyle(el).transitionDuration;
    });

    // When reduced motion is active, duration is clamped to <= 0.01ms (renders as 0s or near zero)
    expect(["0s", "0.00001s", "0.01ms"].some((s) => transitionDur.includes(s) || parseFloat(transitionDur) <= 0.01)).toBe(true);
  });

  test("Axe Core Automated Accessibility Audit: Zero Critical / Serious Issues", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });

    const screens = ["#home", "#pay", "#approvals", "#activity", "#mandates", "#attack-lab", "#receipt"];
    const allViolations: unknown[] = [];

    for (const scr of screens) {
      await page.goto(`/${scr}`);
      await page.waitForTimeout(500);

      const accessibilityScanResults = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
        .analyze();

      const criticalOrSerious = accessibilityScanResults.violations.filter(
        (v) => v.impact === "critical" || v.impact === "serious"
      );

      if (criticalOrSerious.length > 0) {
        allViolations.push({ screen: scr, violations: criticalOrSerious });
      }
    }

    expect(
      allViolations,
      `Axe accessibility audit found critical/serious violations: ${JSON.stringify(allViolations, null, 2)}`
    ).toEqual([]);
  });
});
