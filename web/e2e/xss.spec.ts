import { test, expect } from "@playwright/test";

test.describe("Hostile UI Security Tests: Stored XSS Mitigation", () => {
  const XSS_PURPOSE = `<script>window.__xss_purpose_executed=true</script><img src="x" onerror="window.__xss_purpose_executed=true" />`;
  const XSS_RECIPIENT = `<script>window.__xss_recipient_executed=true</script><b onmouseover="window.__xss_recipient_executed=true">xss_vendor</b>`;
  const XSS_INVOICE = `<script>window.__xss_invoice_executed=true</script>`;

  test("Stored XSS via purpose and payee in Approvals Queue renders inertly", async ({ page, request }) => {
    // 1. Obtain demo agent token
    const tokenRes = await request.post("http://localhost:8000/v1/auth/demo-token", {
      data: { role: "agent", principal_id: "principal_treasury", agent_id: "agent-auto-1" },
    });
    expect(tokenRes.ok()).toBeTruthy();
    const { access_token } = await tokenRes.json();

    // 2. Submit payment intent with stored XSS payloads triggering STEP_UP
    const reqRes = await request.post("http://localhost:8000/v1/payment-requests", {
      data: {
        agent_id: "agent-auto-1",
        recipient_id: XSS_RECIPIENT,
        amount_minor: 125000, // $1,250.00 triggers STEP_UP (> $500 threshold)
        currency: "USD",
        purpose: XSS_PURPOSE,
        idempotency_key: `xss_stepup_${Date.now()}`,
      },
      headers: { Authorization: `Bearer ${access_token}` },
    });
    expect(reqRes.ok()).toBeTruthy();
    const reqData = await reqRes.json();
    expect(reqData.decision).toBe("STEP_UP");

    // 3. Navigate to approvals page in browser
    await page.goto("/#approvals");

    // Wait for approvals list to load
    await expect(page.getByRole("heading", { name: "Human Supervisor Step-Up Review Queue" })).toBeVisible();

    // Wait for network idle / approval card
    await page.waitForTimeout(1000);

    // Verify window globals were NOT set by injected script
    const xssPurposeExecuted = await page.evaluate(() => (window as unknown as { __xss_purpose_executed?: boolean }).__xss_purpose_executed);
    const xssRecipientExecuted = await page.evaluate(() => (window as unknown as { __xss_recipient_executed?: boolean }).__xss_recipient_executed);

    expect(xssPurposeExecuted).toBeUndefined();
    expect(xssRecipientExecuted).toBeUndefined();

    // Verify that the payload is rendered literally as inert text in the DOM
    const rawContent = await page.content();
    expect(rawContent).not.toContain("<script>window.__xss_purpose_executed=true</script>");
    // Escaped entities should appear instead: &lt;script&gt;
    expect(rawContent).toContain("&lt;script&gt;window.__xss_purpose_executed=true&lt;/script&gt;");
  });

  test("Stored XSS in Activity feed and Cryptographic Receipt renders inertly", async ({ page, request }) => {
    // 1. Obtain demo agent token
    const tokenRes = await request.post("http://localhost:8000/v1/auth/demo-token", {
      data: { role: "agent", principal_id: "principal_treasury", agent_id: "agent-auto-1" },
    });
    expect(tokenRes.ok()).toBeTruthy();
    const { access_token } = await tokenRes.json();

    // 2. Submit instant payment intent ($20.00) with stored XSS
    const reqRes = await request.post("http://localhost:8000/v1/payment-requests", {
      data: {
        agent_id: "agent-auto-1",
        recipient_id: XSS_RECIPIENT,
        amount_minor: 2000,
        currency: "USD",
        purpose: `${XSS_PURPOSE} ref: ${XSS_INVOICE}`,
        idempotency_key: `xss_act_${Date.now()}`,
      },
      headers: { Authorization: `Bearer ${access_token}` },
    });
    expect(reqRes.ok()).toBeTruthy();
    const reqData = await reqRes.json();
    expect(reqData.decision).toBe("ALLOW");

    // 3. Navigate to Activity page
    await page.goto("/#activity");
    await expect(page.getByRole("heading", { name: "Cryptographic Shield-Wall Ledger" })).toBeVisible();
    await page.waitForTimeout(1000);

    // Verify window globals are undefined
    const xssPurposeExecuted = await page.evaluate(() => (window as unknown as { __xss_purpose_executed?: boolean }).__xss_purpose_executed);
    const xssRecipientExecuted = await page.evaluate(() => (window as unknown as { __xss_recipient_executed?: boolean }).__xss_recipient_executed);
    const xssInvoiceExecuted = await page.evaluate(() => (window as unknown as { __xss_invoice_executed?: boolean }).__xss_invoice_executed);

    expect(xssPurposeExecuted).toBeUndefined();
    expect(xssRecipientExecuted).toBeUndefined();
    expect(xssInvoiceExecuted).toBeUndefined();

    // 4. Navigate to Receipt view
    await page.goto(`/#receipt`);
    await page.locator("input[placeholder*='receipt']").fill(reqData.event_id || reqData.request_id);
    await page.getByRole("button", { name: /Verify Proof/i }).click();

    await page.waitForTimeout(1000);

    // Verify scripts still haven't run
    const xssAfterReceipt = await page.evaluate(() => (window as unknown as { __xss_purpose_executed?: boolean }).__xss_purpose_executed);
    expect(xssAfterReceipt).toBeUndefined();
  });
});
