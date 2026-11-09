import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { chromium } from "playwright";

const site = "http://localhost:5173";
const api = "http://localhost:8080/api/v1";
const full = process.env.KNOTDEVT_E2E_WRITE === "1";
const existingJob = process.env.KNOTDEVT_E2E_JOB;
const password = process.env.KNOTDEVT_DEMO_PASSWORD;
const screenshots = process.env.KNOTDEVT_E2E_SCREENSHOTS;
const browser = await chromium.launch({
  channel: process.env.KNOTDEVT_BROWSER || "msedge",
});
const errors = [];

async function capture(page, name) {
  if (screenshots)
    await page.screenshot({ path: join(screenshots, name + ".png") });
}

async function read(page, path) {
  return page.evaluate(async (url) => {
    const response = await fetch(url, { credentials: "include" });
    if (!response.ok) throw new Error("API HTTP " + response.status);
    return response.json();
  }, api + path);
}

function watch(page, suffix, method) {
  return page.waitForResponse(
    (response) =>
      response.url().endsWith(suffix) && response.request().method() === method,
  );
}

async function login(page, identity) {
  await page.getByLabel("Email").fill(identity + "@knotdevt.test");
  await page.getByLabel("Password").fill(password);
  const response = watch(page, "/auth/login", "POST");
  await page.getByRole("button", { name: "Sign in" }).click();
  assert.equal((await response).status(), 200);
  await page.getByRole("heading", { name: "Assigned projects" }).waitFor();
}

async function chooseProject(page) {
  await page.getByRole("button", { name: /College event payments/ }).click();
  await page.getByRole("heading", { name: "Evidence Tree" }).waitFor();
  return new URL(page.url()).searchParams.get("project");
}

function nav(page, name) {
  return page
    .getByRole("navigation", { name: "Workspace navigation" })
    .getByRole("button", { name, exact: true });
}

try {
  const reviewer = await browser.newPage({
    viewport: { width: 1440, height: 960 },
  });
  const recipient = await browser.newPage({
    reducedMotion: "reduce",
    viewport: { width: 390, height: 844 },
    isMobile: true,
    hasTouch: true,
  });
  for (const page of [reviewer, recipient]) {
    page.setDefaultTimeout(40000);
    page.on("pageerror", (error) => errors.push(error.message));
    await page.goto(site, { waitUntil: "networkidle", timeout: 60000 });
    await page.getByRole("heading", { name: /Knowledge shouldn/i }).waitFor();
    assert.equal(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
      true,
    );
  }
  await capture(reviewer, "landing");
  await reviewer.getByRole("link", { name: "Login", exact: true }).click();
  await reviewer.locator(".route-wipe").waitFor({ state: "visible" });
  await capture(reviewer, "blue-login-transition");
  await reviewer.waitForURL("**/login");
  await recipient.getByRole("link", { name: "Login", exact: true }).click();
  await recipient.waitForURL("**/login");
  await capture(reviewer, "login");
  console.log(
    "PASS desktop blue transition, mobile layout and reduced-motion navigation",
  );

  if (password) {
    await login(reviewer, "reviewer");
    const project = await chooseProject(reviewer);
    await capture(reviewer, "workspace");
    await login(recipient, "recipient");
    const identity = await read(recipient, "/auth/me");
    assert.equal(await chooseProject(recipient), project);
    assert.equal(await nav(recipient, "Review Queue").count(), 0);
    console.log(
      "PASS real reviewer and recipient login, session recovery, discovery and role-aware dashboard",
    );

    await nav(reviewer, "Sources").click();
    await reviewer.getByRole("button", { name: /PAY-21/ }).click();
    await reviewer.getByText(/Friday deployment was proposed/).waitFor();
    console.log("PASS authorized source exploration");

    if (full) {
      const fixture = readFileSync(
        new URL("../../backend/tests/fixtures/issues.json", import.meta.url),
        "utf8",
      );
      await reviewer.getByRole("textbox", { name: "JSON batch" }).fill(fixture);
      await reviewer
        .getByRole("checkbox", { name: /permission to import/ })
        .check();
      await reviewer.getByRole("button", { name: "Queue import" }).click();
      await reviewer
        .getByRole("button", { name: "Refresh source library" })
        .waitFor();
      console.log("PASS synthetic import via Celery");

      await nav(reviewer, "AI Workflow").click();
      let jobId = existingJob;
      if (jobId) {
        await reviewer
          .getByText("Open an existing job", { exact: true })
          .click();
        await reviewer.getByLabel("Job ID").fill(jobId);
        await reviewer
          .getByRole("button", { name: "Open", exact: true })
          .click();
      } else {
        await reviewer
          .getByLabel("Handover task")
          .fill("Prepare the event-registration payment release");
        await reviewer
          .getByLabel("Assigned recipient IDs")
          .fill(identity.user_id);
        const queued = watch(reviewer, "/agent-jobs", "POST");
        await reviewer.getByRole("button", { name: "Run workflow" }).click();
        const response = await queued;
        assert.equal(response.status(), 202);
        jobId = (await response.json()).id;
      }
      console.log("Agent job " + jobId);
      try {
        await reviewer
          .getByText("Human review checkpoint", { exact: true })
          .waitFor({ timeout: 115000 });
      } catch (error) {
        const runs = await read(reviewer, "/jobs/" + jobId + "/runs");
        console.log(
          runs.map(({ role, status, error_code }) => ({
            role,
            status,
            error_code,
          })),
        );
        throw error;
      }
      assert.equal(
        await reviewer
          .locator(".agent-list > li > .flow > .row > .badge.success")
          .count(),
        5,
      );
      await capture(reviewer, "workflow");
      await reviewer.getByRole("button", { name: "Open review draft" }).click();
      const form = reviewer
        .locator("form")
        .filter({
          has: reviewer.getByRole("heading", { name: "Critical-gap review" }),
        });
      await form.waitFor();
      const draftId = new URL(reviewer.url()).searchParams.get("draft");
      let draft = await read(reviewer, "/drafts/" + draftId);
      await reviewer
        .getByRole("button", { name: "Inspect evidence" })
        .first()
        .click();
      await reviewer.locator(".evidence-column .claim-root").waitFor();
      assert.ok(await reviewer.locator(".evidence-column .tree li").count());
      const original = reviewer
        .locator("article")
        .filter({
          has: reviewer.getByRole("button", { name: "Correct claim" }),
        })
        .first();
      await original.getByRole("button", { name: "Correct claim" }).click();
      await original
        .getByRole("textbox", { name: "Reason for correction" })
        .fill("Verified the synthetic claim and retained its exact citations.");
      const patched = reviewer.waitForResponse(
        (item) =>
          item.url().includes("/claims/") &&
          item.request().method() === "PATCH",
      );
      await original.getByRole("button", { name: "Save correction" }).click();
      assert.equal((await patched).status(), 200);
      await reviewer
        .getByText(new RegExp("Draft revision " + (draft.revision + 1)))
        .waitFor();
      draft = await read(reviewer, "/drafts/" + draftId);
      for (const [index, { claim }] of draft.claims.entries()) {
        const field = form.locator("fieldset").nth(index);
        const critical = ["blocker", "prerequisite"].includes(claim.kind);
        await field
          .getByLabel("Classification")
          .selectOption(critical ? claim.kind : "non_critical");
        if (critical)
          await field.getByLabel("Disposition").selectOption("unverified");
        await field
          .getByLabel("Rationale")
          .fill(
            "Reviewed the claim snapshot. The separate approval gap tracks the missing testing sign-off.",
          );
      }
      await form
        .getByRole("button", { name: "Add evidence-backed gap" })
        .click();
      const gap = form.getByRole("group", { name: "Additional gap 1" });
      const sources = await read(reviewer, "/projects/" + project + "/sources");
      const approvalSource = sources.items.find(
        (source) => source.original_id === "M-07",
      );
      assert.ok(
        approvalSource &&
          draft.source_revision_ids.includes(approvalSource.revision_id),
      );
      await gap.getByLabel("Disposition").selectOption("blocking");
      await gap
        .getByLabel("Source revision")
        .selectOption(approvalSource.revision_id);
      await gap
        .getByLabel("Rationale")
        .fill(
          "Monday approval requires testing sign-off, which is absent in the synthetic evidence.",
        );
      const approve = form.getByRole("button", {
        name: "Approve immutable handover",
      });
      assert.equal(await approve.isDisabled(), true);
      await form
        .getByRole("checkbox", { name: /confirm the exact source/ })
        .check();
      await capture(reviewer, "review");
      const approving = watch(reviewer, "/approve", "POST");
      await approve.click();
      const approval = await approving;
      assert.ok(approval.ok(), "Approval HTTP " + approval.status());
      const version = await approval.json();
      await reviewer
        .getByRole("heading", { name: "Approved handover" })
        .waitFor();
      console.log(
        "PASS five agents, Evidence Tree, claim correction, critical-gap confirmation and immutable approval",
      );

      await nav(recipient, "Handover Versions").click();
      await recipient
        .getByRole("button", {
          name: /Prepare the event-registration payment release/,
        })
        .first()
        .waitFor();
      const detail = new URL(recipient.url());
      detail.searchParams.set("version", version.id);
      await recipient.goto(detail.toString());
      await recipient
        .getByRole("heading", { name: "Handover claims" })
        .waitFor();
      const claim =
        version.handover.claims.find((item) => item.kind === "decision") ??
        version.handover.claims[0];
      await recipient
        .getByRole("button", { name: claim.statement, exact: false })
        .click();
      await recipient.locator(".evidence-column .citation").first().waitFor();
      await recipient
        .getByRole("button", { name: "Acknowledge handover" })
        .click();
      await recipient.getByText(/^Acknowledged /).waitFor();
      await recipient
        .getByRole("button", { name: "Open Readiness Test" })
        .click();
      for (const question of draft.proposed_rubric.questions) {
        await recipient
          .locator('input[name="' + question.dimension + '"]')
          .nth(question.correct_choice)
          .check();
      }
      await recipient.getByRole("button", { name: "Review answers" }).click();
      await recipient
        .getByRole("button", { name: "Submit assessment" })
        .click();
      await recipient
        .getByRole("heading", { name: "Readiness result" })
        .waitFor();
      assert.equal(
        await recipient.locator(".score strong").textContent(),
        "100",
      );
      assert.equal(
        await recipient.locator(".package-status .badge").textContent(),
        "blocked by project gap",
      );
      assert.equal(
        await recipient.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
        true,
      );
      await capture(recipient, "readiness-mobile");
      console.log(
        "PASS recipient Context Trace, receipt and 100/100 blocked assessment",
      );
    }

    await recipient.getByRole("button", { name: "Log out" }).click();
    await recipient.waitForURL("**/login");
    await recipient.goto(site + "/app");
    await recipient
      .getByRole("heading", { name: "Sign in to continue" })
      .waitFor();
    console.log("PASS logout and unauthenticated workspace");
  } else if (full) {
    throw new Error(
      "Full browser verification requires the existing local demo password.",
    );
  }
  assert.deepEqual(errors, []);
} finally {
  await browser.close();
}
