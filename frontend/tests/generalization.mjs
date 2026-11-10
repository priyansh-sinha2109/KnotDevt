import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { chromium } from "playwright";

const site = "http://localhost:3000";
const api = "http://localhost:8080/api/v1";
const output = process.env.KNOTDEVT_GENERALIZATION_OUTPUT || process.env.TEMP;
const allCases = [
  ["Playwright ARM64", "https://github.com/microsoft/playwright/issues/43998"],
  ["Pandas PyArrow", "https://github.com/pandas-dev/pandas/issues/71515"],
  ["Playwright HAR", "https://github.com/microsoft/playwright/issues/44006"],
  ["WALA Dashboard", "https://github.com/wala/WALA/issues/2119"],
];
const start = Number.parseInt(process.env.KNOTDEVT_GENERALIZATION_START || "0", 10);
const limit = Number.parseInt(process.env.KNOTDEVT_GENERALIZATION_LIMIT || "4", 10);
const cases = allCases.slice(
  Math.max(0, Math.min(start, allCases.length - 1)),
  Math.max(0, Math.min(start, allCases.length - 1)) + Math.max(1, Math.min(limit, allCases.length)),
);

const browser = await chromium.launch({ channel: process.env.KNOTDEVT_BROWSER || "msedge" });
const owner = await browser.newPage({ viewport: { width: 1440, height: 900 } });
const recipient = await browser.newPage({ viewport: { width: 390, height: 844 }, reducedMotion: "reduce" });
const errors = [];
for (const page of [owner, recipient]) {
  page.setDefaultTimeout(45000);
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (entry) => {
    if (entry.type() === "error" && !entry.text().startsWith("Failed to load resource:")) errors.push(entry.text());
  });
}

async function register(page, email, password) {
  await page.goto(site + "/login");
  await page.getByRole("button", { name: "Create account", exact: true }).click();
  await page.locator('input[name="email"]').fill(email);
  await page.locator('input[name="password"]').fill(password);
  await page.getByRole("button", { name: "Create account", exact: true }).click();
  await page.waitForURL("**/app");
}

async function request(page, path, { method = "GET", body } = {}) {
  return page.evaluate(async ({ url, method, body }) => {
    const me = await fetch("http://localhost:8080/api/v1/auth/me", { credentials: "include" });
    if (!me.ok) throw new Error(`Session HTTP ${me.status}`);
    const identity = await me.json();
    const response = await fetch(url, {
      method,
      credentials: "include",
      headers: body === undefined ? { "X-CSRF-Token": identity.csrf_token } : {
        "Content-Type": "application/json",
        "X-CSRF-Token": identity.csrf_token,
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const text = await response.text();
    const data = text ? JSON.parse(text) : null;
    if (!response.ok) throw new Error(`API ${method} ${url} HTTP ${response.status}: ${text}`);
    return data;
  }, { url: api + path, method, body });
}

async function waitJob(page, id, timeout = 150000) {
  const end = Date.now() + timeout;
  while (Date.now() < end) {
    const job = await request(page, `/jobs/${id}`);
    if (job.state === "succeeded" || job.state === "failed") return job;
    await page.waitForTimeout(750);
  }
  throw new Error(`Timed out waiting for job ${id}`);
}

function snapshotText(issue) {
  return [
    `GitHub issue ${issue.repository}#${issue.number}`,
    `Title: ${issue.title}`,
    `State at snapshot: ${issue.state}`,
    `Author: ${issue.author}`,
    `Assignees: ${issue.assignees.length ? issue.assignees.join(", ") : "None listed"}`,
    `Created: ${issue.created_at}`,
    `Updated: ${issue.updated_at}`,
    `Closed: ${issue.closed_at || "Not closed"}`,
    "",
    issue.body,
  ].join("\n");
}

function caseFile(name) {
  return name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

async function importBatch(page, project, batch) {
  const job = await request(page, `/projects/${project}/imports`, { method: "POST", body: batch });
  const result = await waitJob(page, job.id, 45000);
  assert.equal(result.state, "succeeded", `import ${job.id}`);
}

async function createProject(workspace, name) {
  return request(owner, `/workspaces/${workspace}/projects`, { method: "POST", body: { name } });
}

function evaluateCitations(runs) {
  const context = runs.find((run) => run.role === "context_collector" && run.status === "succeeded")?.output;
  const audit = runs.find((run) => run.role === "evidence_auditor" && run.status === "succeeded")?.output;
  if (!context || !audit) return { total: 0, exact: 0, invalid: 0 };
  const revisions = new Map(context.evidence.map((item) => [item.revision_id, item.excerpt]));
  let total = 0;
  let exact = 0;
  for (const claim of audit.claims) for (const pointer of claim.content.evidence) {
    total += 1;
    const text = revisions.get(pointer.revision_id) || "";
    if (Array.from(text).slice(pointer.start, pointer.end).join("") === pointer.quote) exact += 1;
  }
  return { total, exact, invalid: total - exact };
}

const ownerEmail = `general-owner-${randomUUID()}@test.invalid`;
const recipientEmail = `general-recipient-${randomUUID()}@test.invalid`;
const password = `Audit-${randomUUID()}!`;
const report = { started_at: new Date().toISOString(), cases: [], browser_errors: errors };

try {
  await register(owner, ownerEmail, password);
  const workspace = await request(owner, "/workspaces", { method: "POST", body: { name: "Generalization audit" } });
  const first = await createProject(workspace.id, cases[0][0]);
  const invite = await request(owner, `/projects/${first.id}/invitations`, { method: "POST", body: { email: recipientEmail } });
  await register(recipient, recipientEmail, password);
  await request(recipient, "/invitations/redeem", { method: "POST", body: { code: invite.code } });
  const identity = await request(recipient, "/auth/me");

  for (let index = 0; index < cases.length; index += 1) {
    const [name, reference] = cases[index];
    const project = index === 0 ? first : await createProject(workspace.id, name);
    if (index > 0) await request(owner, `/projects/${project.id}/recipients`, { method: "POST", body: { email: recipientEmail } });
    const sourceId = `github-${new URL(reference).pathname.split("/").at(-1)}-reference`;
    await importBatch(owner, project.id, {
      kind: "issue-events",
      provider: "manual",
      events: [{ source_id: sourceId, author: "Generalization audit", event_at: new Date().toISOString(), reference, text: `Public GitHub issue reference for ${name}.`, related_ids: [], access: "project", event_type: "task" }],
    });
    const listed = await request(owner, `/projects/${project.id}/sources?query=${encodeURIComponent(sourceId)}`);
    const snapshot = await request(owner, `/sources/${listed.items[0].id}/public-issue`, { method: "POST" });
    const exactId = `github-${snapshot.repository.replace("/", "-")}-${snapshot.number}-snapshot`;
    await importBatch(owner, project.id, {
      kind: "issue-events",
      provider: "github-public",
      events: [{ source_id: exactId, author: snapshot.author, event_at: snapshot.updated_at, reference, text: snapshotText(snapshot), related_ids: [], access: "project", event_type: "task" }],
    });
    const queued = await request(owner, `/projects/${project.id}/agent-jobs`, { method: "POST", body: { task: `Prepare a source-grounded handover for ${name}`, audience: [identity.user_id], source_ids: [exactId] } });
    const job = await waitJob(owner, queued.id);
    const runs = await request(owner, `/jobs/${queued.id}/runs`);
    const row = { name, reference, retrieved_at: snapshot.retrieved_at, snapshot_sha256: snapshot.snapshot_sha256, project_id: project.id, job_id: queued.id, job_state: job.state, job_error: job.error_code, runs, citations: evaluateCitations(runs) };
    if (job.state === "succeeded") {
      row.draft = await request(owner, `/projects/${project.id}/drafts`, { method: "POST", body: { agent_job_id: queued.id } });
      report.cases.push(row);
      if (index < 2) {
        await owner.goto(`${site}/app?workspace=${workspace.id}&project=${project.id}&view=review&draft=${row.draft.id}`);
        await owner.getByRole("heading", { name: "Critical-gap review" }).waitFor();
        const article = owner.locator("article").filter({ has: owner.getByRole("button", { name: "Explore Evidence", exact: true }) }).first();
        await article.getByRole("button", { name: "Explore Evidence", exact: true }).click();
        const explorer = owner.getByRole("dialog", { name: "Evidence Explorer" });
        await explorer.waitFor();
        const nodes = explorer.locator(".react-flow__node");
        await owner.waitForTimeout(1200);
        if (await nodes.count()) await explorer.locator(".react-flow__controls-fitview").click();
        await owner.screenshot({ path: join(output, `generalization-${caseFile(name)}-explorer.png`), fullPage: true });
        row.browser_nodes = await nodes.count();
        await explorer.getByRole("button", { name: "Close explorer" }).click();
        await owner.screenshot({ path: join(output, `generalization-${caseFile(name)}-review.png`), fullPage: true });
      }
    } else report.cases.push(row);
    console.log(`${name}: ${job.state}${job.error_code ? ` (${job.error_code})` : ""}`);
    if (job.state === "failed") break;
  }
  report.finished_at = new Date().toISOString();
  assert.deepEqual(errors, []);
} finally {
  writeFileSync(join(output, "knotdevt-generalization-browser.json"), JSON.stringify(report, null, 2));
  await browser.close();
}
