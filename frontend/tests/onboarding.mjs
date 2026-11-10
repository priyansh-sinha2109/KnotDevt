import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { chromium } from "playwright";

const browser = await chromium.launch({ channel: "msedge" });
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const base = process.env.KNOTDEVT_FRONTEND_URL ?? "http://localhost:3000";
  await page.goto(`${base}/login`);
  await page.getByRole("button", { name: "Create account", exact: true }).click();
  await page.locator('input[name="email"]').fill(`edge-${randomUUID()}@test.invalid`);
  await page.locator('input[name="password"]').fill(randomUUID());
  const registered = page.waitForResponse((response) => response.url().endsWith("/auth/register") && response.request().method() === "POST");
  const signedIn = page.waitForResponse((response) => response.url().endsWith("/auth/login") && response.request().method() === "POST");
  await page.getByRole("button", { name: "Create account", exact: true }).click();
  assert.equal((await registered).status(), 204, "Registration HTTP status");
  assert.equal((await signedIn).status(), 200, "Sign-in HTTP status");
  await page.waitForURL("**/app");
  await page.getByLabel("Workspace name").fill("Synthetic Edge workspace");
  await page.getByRole("button", { name: "Create workspace", exact: true }).click();
  await page.getByRole("heading", { name: "Synthetic Edge workspace" }).waitFor();
  const project = page.getByLabel("Project name");
  if (!(await project.isVisible())) await page.getByText("Set up your workspace", { exact: true }).click();
  await project.fill("Synthetic Edge project");
  await page.getByRole("button", { name: "Create project", exact: true }).click();
  await page.getByRole("heading", { name: "Synthetic Edge project" }).waitFor();
  for (const [width, height] of [[1440, 900], [1280, 800], [768, 1024], [390, 844]]) {
    await page.setViewportSize({ width, height });
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), `Horizontal overflow at ${width}`);
    await page.screenshot({ path: join(tmpdir(), `knotdevt-edge-setup-${width}.png`) });
  }
  console.log("PASS registration, login, workspace and project creation at four viewport sizes");
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.locator(".quick-card").filter({ hasText: "Sources" }).click();
  for (const mode of ["task", "meeting", "message"]) {
    const author = `Synthetic Edge ${mode} author`;
    await page.getByLabel("What would you like to add?").selectOption(mode);
    await page.getByLabel("Written by").fill(author);
    await page.getByLabel("When did it happen?").fill("2026-11-10T09:00");
    await page.getByLabel("Link to the original").fill("https://example.invalid/knotdevt-test");
    await page.getByLabel("What happened?").fill(`Synthetic ${mode} for verifying guided import.`);
    await page.getByRole("checkbox", { name: /I have permission/ }).check();
    const queued = page.waitForResponse((response) => response.url().endsWith("/imports") && response.request().method() === "POST");
    await page.getByRole("button", { name: "Queue import" }).click();
    assert.equal((await queued).status(), 202);
    await page.getByText(author, { exact: false }).waitFor({ timeout: 45_000 });
  }
  await page.screenshot({ path: join(tmpdir(), "knotdevt-edge-guided-import.png") });
  console.log("PASS guided task, meeting and conversation entry with persisted imports");

  const invitee = await browser.newPage();
  const email = `edge-recipient-${randomUUID()}@test.invalid`;
  await invitee.goto(`${base}/login`);
  await invitee.getByRole("button", { name: "Create account", exact: true }).click();
  await invitee.locator('input[name="email"]').fill(email);
  await invitee.locator('input[name="password"]').fill(randomUUID());
  await invitee.getByRole("button", { name: "Create account", exact: true }).click();
  await invitee.waitForURL("**/app");
  await invitee.getByText("No assigned workspaces.", { exact: true }).waitFor();
  await page.bringToFront();
  await page.getByRole("button", { name: "Overview", exact: true }).click();
  await page.context().grantPermissions(["clipboard-read", "clipboard-write"], { origin: base });
  await page.getByRole("button", { name: "Invite teammate", exact: true }).click();
  const invitation = page.getByRole("dialog", { name: "Invite teammate" });
  await invitation.getByLabel("Teammate email").fill(email);
  await invitation.getByLabel("Role", { exact: true }).selectOption({ label: "Recipient" });
  const issued = page.waitForResponse((response) => response.url().endsWith("/invitations") && response.request().method() === "POST");
  await invitation.getByRole("button", { name: "Create invitation" }).click();
  assert.equal((await issued).status(), 201);
  const code = await invitation.getByLabel("Invitation code").inputValue();
  assert.equal(code.length, 43);
  const previousClipboard = await page.evaluate(() => navigator.clipboard.readText());
  try {
    await invitation.getByRole("button", { name: "Copy invitation" }).click();
    await invitation.getByRole("status").filter({ hasText: "Invitation copied" }).waitFor();
    assert.ok(await page.evaluate(async (expected) => (await navigator.clipboard.readText()) === expected, code));
  } finally {
    await page.evaluate((previous) => navigator.clipboard.writeText(previous), previousClipboard);
  }
  assert.ok(!page.url().includes(code), "The invitation code must stay out of the URL");
  await invitation.getByRole("button", { name: "Close", exact: true }).click();
  await invitee.getByLabel("Invitation code").fill(code.slice(0, -1));
  await invitee.getByRole("button", { name: "Join project" }).click();
  await invitee.getByRole("alert").filter({ hasText: "Paste the full 43-character invitation code" }).waitFor();
  await invitee.getByLabel("Invitation code").fill(`  ${code}  `);
  await invitee.getByRole("button", { name: "Join project" }).click();
  await invitee.getByRole("heading", { name: "Synthetic Edge project" }).waitFor();
  const selected = invitee.getByRole("combobox", { name: "Project", exact: true });
  assert.equal(await selected.evaluate((select) => select.selectedOptions[0]?.text), "Synthetic Edge project");
  await invitee.locator(".workspace-hero").getByText(/^recipient$/i).waitFor();
  assert.equal(await invitee.getByRole("button", { name: "Invite teammate" }).count(), 0);
  await page.getByRole("navigation", { name: "Workspace navigation" })
    .getByRole("button", { name: "AI Workflow", exact: true }).click();
  await page.getByRole("checkbox", { name: email }).check();
  assert.equal(await page.getByRole("checkbox", { name: email }).isChecked(), true);
  console.log("PASS private invitation redemption and assigned recipient selection");
} finally {
  await browser.close();
}
