import { test, expect } from "@playwright/test";

test.describe("PHALANX Operator Dashboard E2E Smoke Tests", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
  });

  test("Scene 1: Request Console - Preset selection and policy dispatch", async ({ page }) => {
    await expect(page.locator("h1.brand-shield")).toHaveText("PHALANX");
    await expect(page.getByText("PAYPAL SANDBOX GUARD ACTIVE")).toBeVisible();

    // Verify presets exist
    const presetBtn = page.getByRole("button", { name: "Under Limit ($25 - ALLOW)" });
    await expect(presetBtn).toBeVisible();
    await presetBtn.click();

    // Verify intent card values
    await expect(page.locator(".intent-card")).toBeVisible();
    const submitBtn = page.getByRole("button", { name: "Evaluate & Submit Intent to Policy Core" });
    await expect(submitBtn).toBeVisible();
    await submitBtn.click();

    // Decision badge renders
    await expect(page.locator(".decision-card")).toBeVisible();
  });

  test("Scene 2: Step-Up Approvals - Role locking and anti-tamper digest", async ({ page }) => {
    // Navigate to Scene 2
    const approvalsTab = page.getByRole("tab", { name: /Scene 2: Step-Up Approvals/i });
    await approvalsTab.click();

    await expect(page.getByRole("heading", { name: "Human Supervisor Step-Up Review Queue" })).toBeVisible();
    await expect(page.getByText("req_stepup_1001")).toBeVisible();

    // Switch persona to AGENT
    const agentRadio = page.getByRole("radio", { name: "AGENT" });
    await agentRadio.click();

    // Verify role lock warning and disabled approval button
    await expect(page.locator(".warning-banner")).toBeVisible();
    const approveBtn = page.getByRole("button", { name: "Authorize Transaction" });
    await expect(approveBtn).toBeDisabled();

    // Switch back to APPROVER
    const approverRadio = page.getByRole("radio", { name: "APPROVER" });
    await approverRadio.click();
    await expect(approveBtn).toBeEnabled();

    // Test tamper toggle
    const tamperToggle = page.getByRole("button", { name: /Test Digest Tamper Diff/i });
    await expect(tamperToggle).toBeVisible();
    await tamperToggle.click();
    await expect(page.locator(".diff-view")).toBeVisible();
  });

  test("Scene 3: Cryptographic Audit Ledger - Chain-of-blocks and tamper detection", async ({ page }) => {
    // Navigate to Scene 3
    const ledgerTab = page.getByRole("tab", { name: /Scene 3: Cryptographic Audit Ledger/i });
    await ledgerTab.click();

    await expect(page.getByRole("heading", { name: "Cryptographic Shield-Wall Ledger" })).toBeVisible();
    await expect(page.locator(".chain-blocks")).toBeVisible();
    await expect(page.getByText("Block #1")).toBeVisible();
    await expect(page.getByText("Block #2")).toBeVisible();
    await expect(page.getByText("Block #3")).toBeVisible();

    // Verify chain integrity
    const verifyBtn = page.getByRole("button", { name: /Verify Chain/i });
    await expect(verifyBtn).toBeVisible();

    // Simulate tampering
    const tamperBtn = page.getByRole("button", { name: "Simulate Database Tamper" });
    await tamperBtn.click();

    // Chain status should turn broken/red
    await expect(page.locator(".integrity-status-bar.red")).toBeVisible();

    // Restore true ledger
    const restoreBtn = page.getByRole("button", { name: "Restore True Ledger" });
    await restoreBtn.click();
    await expect(page.locator(".integrity-status-bar.green")).toBeVisible();
  });

  test("Mandate View - Active Ed25519 Parameters and Budget Cap", async ({ page }) => {
    const mandateTab = page.getByRole("tab", { name: /Ed25519 Mandate/i });
    await mandateTab.click();

    await expect(page.getByRole("heading", { name: "Active Ed25519 Authority Mandate" })).toBeVisible();
    await expect(page.getByText("mandate_default_astra (v1)")).toBeVisible();
    await expect(page.getByText("principal_astra_treasury")).toBeVisible();
    await expect(page.getByText("Remaining Budget")).toBeVisible();
    await expect(page.locator(".sig-code")).toBeVisible();
  });
});
