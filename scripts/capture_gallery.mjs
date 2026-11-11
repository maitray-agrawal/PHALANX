/**
 * PHALANX Submission Gallery Capture Script
 *
 * Captures high-fidelity, deterministic screenshots of all key operational screens,
 * AI Invoice Agent scenarios, cryptographic proof chains, and mobile views.
 *
 * Invariants:
 * - Uses BASE_URL and ADMIN_TOKEN from environment.
 * - Resets demo state before capturing to ensure deterministic queue & ledger state.
 * - Redacts visible secrets and Bearer tokens before capturing.
 * - Generates standard screenshots in docs/gallery/ and 1500x1000 crops for Devpost in docs/gallery/devpost/.
 */

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const ROOT_DIR = path.resolve(__dirname, "..");

// Dynamically resolve Playwright
let chromium;
try {
  const pw = await import("playwright");
  chromium = pw.chromium;
} catch {
  const pw = await import("../web/node_modules/playwright/index.mjs");
  chromium = pw.chromium;
}

const BASE_URL = process.env.BASE_URL || "http://127.0.0.1:8000";
const ADMIN_TOKEN = process.env.ADMIN_TOKEN || "phx_admin_nxZgx2ok5QX0T_i5bW6i9A";
const SUFFIX = process.env.GALLERY_SUFFIX || "-local";

const GALLERY_DIR = path.join(ROOT_DIR, "docs", "gallery");
const DEVPOST_DIR = path.join(GALLERY_DIR, "devpost");

fs.mkdirSync(GALLERY_DIR, { recursive: true });
fs.mkdirSync(DEVPOST_DIR, { recursive: true });

async function resetDemo() {
  console.log(`[Gallery] Resetting demo state at ${BASE_URL}...`);
  try {
    const res = await fetch(`${BASE_URL}/v1/admin/reset`, {
      method: "POST",
      headers: { "X-Admin-Token": ADMIN_TOKEN },
    });
    if (res.ok) {
      console.log("[Gallery] Demo state reset successfully.");
    } else {
      console.warn(`[Gallery] Demo reset returned status: ${res.status}`);
    }
  } catch (err) {
    console.warn(`[Gallery] Failed to reset demo: ${err.message}`);
  }
}

async function redactSecrets(page) {
  await page.evaluate(() => {
    // Redact tokens, keys, and authorization headers from visible text
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) {
      if (node.nodeValue) {
        node.nodeValue = node.nodeValue
          .replace(/eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+/g, "[REDACTED_ROLE_TOKEN]")
          .replace(/phx_admin_[a-zA-Z0-9_-]+/g, "[REDACTED_ADMIN_TOKEN]")
          .replace(/Bearer\s+[^\s]+/gi, "Bearer [REDACTED]");
      }
    }
  });
}

async function saveCapture(page, name, isMobile = false) {
  await redactSecrets(page);
  const stdPath = path.join(GALLERY_DIR, `${name}${SUFFIX}.png`);
  await page.screenshot({ path: stdPath, fullPage: false });
  console.log(`[Gallery] Saved: ${stdPath}`);

  // 1500x1000 Devpost crop
  const devpostPath = path.join(DEVPOST_DIR, `${name}${SUFFIX}.png`);
  if (!isMobile) {
    await page.screenshot({
      path: devpostPath,
      clip: { x: 0, y: 0, width: 1500, height: 1000 },
    });
  } else {
    // For mobile, screenshot standard mobile canvas
    await page.screenshot({ path: devpostPath });
  }
  console.log(`[Gallery] Saved Devpost crop: ${devpostPath}`);
}

async function main() {
  await resetDemo();

  console.log("[Gallery] Launching Chromium browser...");
  const browser = await chromium.launch({ headless: true });

  // 1. Desktop Context (1920x1080)
  const desktopContext = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    deviceScaleFactor: 1,
  });
  const page = await desktopContext.newPage();
  page.on("console", (msg) => console.log("[Browser Console]", msg.type(), msg.text()));
  page.on("pageerror", (err) => console.error("[Browser Error]", err));

  console.log("[Gallery] Capturing 01: Overview / Dashboard...");
  await page.goto(`${BASE_URL}/#home`, { waitUntil: "networkidle" });
  await page.waitForTimeout(1000);
  await saveCapture(page, "01-overview-desktop");

  console.log("[Gallery] Capturing 02: Invoice Agent - Sample A (ALLOW)...");
  await page.goto(`${BASE_URL}/#invoice-agent`, { waitUntil: "networkidle" });
  await page.waitForTimeout(500);
  const sampleABtn = page.locator("button:has-text('SAMPLE A')").first();
  if (await sampleABtn.isVisible()) await sampleABtn.click();
  const runBtn = page.getByRole("button", { name: "Run Autonomous Extraction" });
  await runBtn.click();
  await page.getByText(/Execution Rail/i).first().waitFor({ timeout: 45000 });
  await page.waitForTimeout(1000);
  await saveCapture(page, "02-invoice-agent-sample-a-desktop");

  console.log("[Gallery] Capturing 03: Invoice Agent - Sample B (STEP_UP)...");
  const sampleBBtn = page.locator("button:has-text('SAMPLE B')").first();
  await sampleBBtn.click();
  await page.waitForTimeout(300);
  await runBtn.click();
  await page.getByText(/Execution Rail/i).first().waitFor({ timeout: 45000 });
  await page.waitForTimeout(1000);
  await saveCapture(page, "03-invoice-agent-sample-b-desktop");

  console.log("[Gallery] Capturing 04: Invoice Agent - Sample C (DENY / Injection)...");
  const sampleCBtn = page.locator("button:has-text('SAMPLE C')").first();
  await sampleCBtn.click();
  await page.waitForTimeout(300);
  await runBtn.click();
  await page.getByText(/Execution Rail/i).first().waitFor({ timeout: 45000 });
  await page.waitForTimeout(1000);
  await saveCapture(page, "04-invoice-agent-sample-c-desktop");

  console.log("[Gallery] Capturing 05: Invoice Agent - Sample D (Impersonation)...");
  const sampleDBtn = page.locator("button:has-text('SAMPLE D')").first();
  await sampleDBtn.click();
  await page.waitForTimeout(300);
  await runBtn.click();
  await page.getByText(/Execution Rail/i).first().waitFor({ timeout: 45000 });
  await page.waitForTimeout(1000);
  await saveCapture(page, "05-invoice-agent-sample-d-desktop");

  console.log("[Gallery] Capturing 06: Approvals Queue...");
  await page.goto(`${BASE_URL}/#approvals`, { waitUntil: "networkidle" });
  await page.waitForTimeout(500);
  const createSampleBtn = page.getByRole("button", { name: "Create sample request" }).first();
  if (await createSampleBtn.isVisible()) {
    await createSampleBtn.click();
    await page.waitForTimeout(1000);
  }
  await page.waitForSelector(".approvals-cards-list article, [data-testid='approval-card']", { timeout: 10000 });
  await page.waitForTimeout(500);
  await saveCapture(page, "06-approvals-queue-desktop");

  console.log("[Gallery] Capturing 07: Approvals Edited-Amount Refusal / Tamper Inspection...");
  const inspectDiffBtn = page.getByRole("button", { name: /Inspect Diff/i }).first();
  if (await inspectDiffBtn.isVisible()) {
    await inspectDiffBtn.click();
    await page.waitForTimeout(300);
    const tamperBtn = page.getByRole("button", { name: "Test Digest Tamper Diff" }).first();
    if (await tamperBtn.isVisible()) {
      await tamperBtn.click();
      await page.waitForTimeout(500);
    }
  }
  await saveCapture(page, "07-approvals-refusal-desktop");

  console.log("[Gallery] Capturing 08: Attack Lab...");
  await page.goto(`${BASE_URL}/#attack-lab`, { waitUntil: "networkidle" });
  await page.waitForTimeout(500);
  const executeSimulationBtn = page.getByRole("button", { name: /Execute Full Attack Simulation/i });
  if (await executeSimulationBtn.isVisible()) {
    await executeSimulationBtn.click();
    await page.waitForTimeout(1200);
  }
  await saveCapture(page, "08-attack-lab-desktop");

  console.log("[Gallery] Capturing 09: Activity Ledger & Receipt Verification...");
  await page.goto(`${BASE_URL}/#activity`, { waitUntil: "networkidle" });
  await page.waitForTimeout(800);
  const verifyChainBtn = page.getByRole("button", { name: /Verify Chain/i }).first();
  if (await verifyChainBtn.isVisible()) {
    await verifyChainBtn.click();
    await page.waitForTimeout(1000);
  }
  await saveCapture(page, "09-activity-ledger-desktop");

  console.log("[Gallery] Capturing 10: Mandates...");
  await page.goto(`${BASE_URL}/#mandates`, { waitUntil: "networkidle" });
  await page.waitForTimeout(800);
  await saveCapture(page, "10-mandates-desktop");

  console.log("[Gallery] Capturing 11: Pay Console with PayPal Sandbox Order...");
  await page.goto(`${BASE_URL}/#pay`, { waitUntil: "networkidle" });
  await page.waitForTimeout(500);
  const presetAllow = page.getByText("Under Limit ($25 - ALLOW)");
  if (await presetAllow.isVisible()) {
    await presetAllow.click();
    await page.waitForTimeout(300);
  }
  const submitPayBtn = page.getByRole("button", { name: "Evaluate & Submit Intent to Policy Core" });
  if (await submitPayBtn.isVisible()) {
    await submitPayBtn.click();
    await page.waitForSelector("[data-testid='decision-badge']", { timeout: 15000 });
    await page.waitForTimeout(1000);
  }
  await saveCapture(page, "11-paypal-sandbox-awaiting-desktop");

  await desktopContext.close();

  // 2. Mobile Context (390x844 - iPhone 14/15 size)
  console.log("[Gallery] Launching Mobile Browser Context (390x844)...");
  const mobileContext = await browser.newContext({
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 2,
    isMobile: true,
    hasTouch: true,
  });
  const mobilePage = await mobileContext.newPage();

  console.log("[Gallery] Capturing 12: Mobile Overview...");
  await mobilePage.goto(`${BASE_URL}/#home`, { waitUntil: "networkidle" });
  await mobilePage.waitForTimeout(800);
  await saveCapture(mobilePage, "12-overview-mobile", true);

  console.log("[Gallery] Capturing 13: Mobile Invoice Agent...");
  await mobilePage.goto(`${BASE_URL}/#invoice-agent`, { waitUntil: "networkidle" });
  await mobilePage.waitForTimeout(800);
  const mRunBtn = mobilePage.getByRole("button", { name: "Run Autonomous Extraction" });
  if (await mRunBtn.isVisible()) {
    await mRunBtn.click();
    await mobilePage.getByText(/Execution Rail/i).first().waitFor({ timeout: 45000 });
    await mobilePage.waitForTimeout(1000);
  }
  await saveCapture(mobilePage, "13-invoice-agent-mobile", true);

  console.log("[Gallery] Capturing 14: Mobile Approvals...");
  await mobilePage.goto(`${BASE_URL}/#approvals`, { waitUntil: "networkidle" });
  await mobilePage.waitForTimeout(800);
  await saveCapture(mobilePage, "14-approvals-mobile", true);

  console.log("[Gallery] Capturing 15: Mobile Activity Ledger...");
  await mobilePage.goto(`${BASE_URL}/#activity`, { waitUntil: "networkidle" });
  await mobilePage.waitForTimeout(800);
  await saveCapture(mobilePage, "15-activity-mobile", true);

  await mobileContext.close();
  await browser.close();

  console.log("[Gallery] All screenshots successfully captured!");
}

main().catch((err) => {
  console.error("[Gallery] Fatal error:", err);
  process.exit(1);
});

