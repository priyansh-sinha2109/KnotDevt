import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { chromium } from "playwright";

const site = "http://localhost:3000";
const api = "http://localhost:8080/api/v1";
const full = process.env.KNOTDEVT_E2E_WRITE === "1";
const personal = full && process.env.KNOTDEVT_E2E_PERSONAL === "1";
const wala = personal && process.env.KNOTDEVT_E2E_WALA === "1";
const task = wala ? "Plan the WALA dependency maintenance handover" : "Prepare the event-registration payment release";
const searchSource = wala ? "WALA-2119-summary" : "PAY-21";
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
  const workspace = page.getByRole("combobox", { name: "Workspace", exact: true });
  await workspace.selectOption({ label: "SoloOne Demo" });
  await page.getByRole("button", { name: /College event payments/ }).click();
  await page.getByRole("heading", { name: "College event payments", exact: true }).waitFor();
  return new URL(page.url()).searchParams.get("project");
}

async function register(page, email) {
  await page.getByRole("button", { name: "Create account", exact: true }).click();
  await page.locator('input[name="email"]').fill(email);
  await page.locator('input[name="password"]').fill(randomUUID());
  await page.getByRole("button", { name: "Create account", exact: true }).click();
  await page.waitForURL("**/app");
  await page.getByText("No assigned workspaces.", { exact: true }).waitFor();
}

async function setupPersonal(reviewer, recipient, email) {
  await register(reviewer, `edge-owner-${randomUUID()}@test.invalid`);
  await reviewer.getByLabel("Workspace name").fill("Edge handover workspace");
  await reviewer.getByRole("button", { name: "Create workspace", exact: true }).click();
  await reviewer.getByRole("heading", { name: "Edge handover workspace" }).waitFor();
  const name = reviewer.getByLabel("Project name");
  if (!(await name.isVisible())) await reviewer.getByText("Set up your workspace", { exact: true }).click();
  await name.fill("Edge payment handover");
  await reviewer.getByRole("button", { name: "Create project", exact: true }).click();
  await reviewer.getByRole("heading", { name: "Edge payment handover", exact: true }).waitFor();
  const project = new URL(reviewer.url()).searchParams.get("project");
  await reviewer.getByRole("button", { name: "Invite teammate", exact: true }).click();
  const invitation = reviewer.getByRole("dialog", { name: "Invite teammate" });
  await invitation.getByLabel("Teammate email").fill(email);
  await invitation.getByRole("button", { name: "Create invitation" }).click();
  const code = await invitation.getByLabel("Invitation code").inputValue();
  await invitation.getByRole("button", { name: "Close", exact: true }).click();
  await register(recipient, email);
  await recipient.getByLabel("Invitation code").fill(code);
  await recipient.getByRole("button", { name: "Join project" }).click();
  await recipient.getByRole("heading", { name: "Edge payment handover", exact: true }).waitFor();
  assert.equal(new URL(recipient.url()).searchParams.get("project"), project);
  console.log("PASS newly registered accounts, project setup and private invitation");
  return project;
}

async function uploadEvidence(page, name) {
  const fixture = readFileSync(new URL(`../../backend/tests/fixtures/${name}`, import.meta.url));
  await page.getByLabel("What would you like to add?").selectOption("file");
  await page.getByLabel("Source export", { exact: true }).setInputFiles({ name, mimeType: "application/json", buffer: fixture });
  await page.getByText(new RegExp(`records in ${name.replace(".", "\\.")}`)).waitFor();
  await page.getByRole("checkbox", { name: /permission to import/ }).check();
  const response = watch(page, "/imports", "POST");
  await page.getByRole("button", { name: "Queue import" }).click();
  const queued = await response;
  assert.equal(queued.status(), 202);
  const { id } = await queued.json();
  await page.waitForFunction(async (url) => {
    const status = await fetch(url, { credentials: "include" });
    if (!status.ok) throw new Error(`Import status HTTP ${status.status}`);
    const job = await status.json();
    if (job.state === "failed") throw new Error(`Import failed: ${job.error_code}`);
    return job.state === "succeeded";
  }, `${api}/jobs/${id}`, { polling: 750 });
  await page.getByRole("button", { name: "Refresh source library" }).waitFor();
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
    page.on("console", (entry) => {
      if (
        entry.type() === "error" &&
        !entry.text().startsWith("Failed to load resource:")
      ) {
        errors.push(entry.text());
      }
    });
    await page.goto(site, { waitUntil: "domcontentloaded", timeout: 60000 });
    const intro = page.locator(".public-intro");
    if (page === reviewer) {
      await intro.waitFor({ state: "visible" });
      await capture(page, "first-load-intro");
      await intro.waitFor({ state: "hidden" });
    } else {
      await page.waitForFunction(() => !document.querySelector(".public-intro")?.getAttribute("style"));
    }
    await page.getByRole("heading", { name: /Knowledge shouldn/i }).waitFor();
    assert.equal(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
      true,
    );
  }
  await capture(reviewer, "landing");
  const pinned = reviewer.locator(".pin-spacer .story");
  await pinned.waitFor();
  const initial = await reviewer
    .locator(".story-card")
    .first()
    .evaluate((card) => getComputedStyle(card).transform);
  await pinned.evaluate((story) => {
    window.scrollTo(
      0,
      story.getBoundingClientRect().top + scrollY + innerHeight * 0.7,
    );
  });
  await reviewer.waitForFunction((before) => {
    const story = document.querySelector(".story");
    const card = document.querySelector(".story-card");
    return (
      story &&
      card &&
      Math.abs(story.getBoundingClientRect().top) < 6 &&
      getComputedStyle(card).transform !== before
    );
  }, initial);
  await reviewer.evaluate(() => window.scrollTo(0, 0));
  await reviewer.waitForFunction(() => scrollY < 3);
  await reviewer
    .getByRole("link", { name: "Inspect evidence for ISSUE · PAY-21" })
    .click();
  assert.equal(
    await reviewer
      .getByRole("button", { name: "ISSUE · PAY-21", exact: true })
      .getAttribute("aria-pressed"),
    "true",
  );
  assert.equal(await recipient.locator(".pin-spacer .story").count(), 0);
  await recipient
    .getByRole("navigation", { name: "Main navigation" })
    .getByRole("link", { name: "Evidence" })
    .waitFor();
  const tablet = await browser.newPage({
    viewport: { width: 768, height: 1024 },
    hasTouch: true,
  });
  await tablet.goto(site);
  assert.equal(
    await tablet.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
    true,
  );
  assert.equal(await tablet.locator(".pin-spacer .story").count(), 0);
  await tablet.close();
  console.log(
    "PASS desktop pin and real scrub, tablet layout, mobile navigation and reduced-motion fallback",
  );
  await reviewer.getByRole("link", { name: "Login", exact: true }).click();
  await reviewer.locator(".route-wipe").waitFor({ state: "visible" });
  await capture(reviewer, "blue-login-transition");
  await reviewer.waitForURL("**/login");
  await reviewer.waitForFunction(
    () =>
      !document.documentElement.classList.contains("lenis") &&
      !document.querySelector(".pin-spacer"),
  );
  await recipient.getByRole("link", { name: "Login", exact: true }).click();
  await recipient.waitForURL("**/login");
  await capture(reviewer, "login");
  console.log(
    "PASS desktop blue transition, mobile layout and reduced-motion navigation",
  );

  if (password || personal) {
    const recipientEmail = personal ? `edge-recipient-${randomUUID()}@test.invalid` : "recipient@knotdevt.test";
    let project;
    if (personal) project = await setupPersonal(reviewer, recipient, recipientEmail);
    else {
      await login(reviewer, "reviewer");
      project = await chooseProject(reviewer);
      await login(recipient, "recipient");
      assert.equal(await chooseProject(recipient), project);
    }
    await reviewer.setViewportSize({ width: 768, height: 1024 });
    await reviewer.getByRole("button", { name: "Use dark theme" }).click();
    await reviewer.locator(".workspace.dark").waitFor();
    assert.equal(
      await reviewer.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
      true,
    );
    await reviewer.getByRole("button", { name: "Use light theme" }).click();
    await reviewer.setViewportSize({ width: 1440, height: 960 });
    await capture(reviewer, "workspace");
    assert.equal(await nav(recipient, "Review Queue").count(), 0);
    const restricted = password ? await browser.newPage() : null;
    if (restricted) {
    try {
      await restricted.goto(site + "/login");
      await login(restricted, "restricted");
      await restricted.getByText(/No projects are assigned/).waitFor();
      const deepLink = new URL(reviewer.url());
      deepLink.searchParams.set("view", "agents");
      await restricted.goto(deepLink.toString());
      await restricted.getByText(/No projects are assigned/).waitFor();
      assert.equal(await nav(restricted, "AI Workflow").count(), 0);
      const status = await restricted.evaluate(
        async (url) => (await fetch(url, { credentials: "include" })).status,
        api + "/projects/" + project,
      );
      assert.equal(status, 404);
      await restricted.getByRole("button", { name: "Log out" }).click();
      await restricted.waitForURL("**/login");
    } finally {
      await restricted.close();
    }
    console.log(
      "PASS reviewer and recipient sessions, project discovery, restricted deep link and backend denial",
    );
    }

    await nav(reviewer, "Sources").click();
    if (wala) {
      await uploadEvidence(reviewer, "wala-dashboard-summary.json");
    } else if (personal) {
      await uploadEvidence(reviewer, "issues.json");
      await uploadEvidence(reviewer, "conversations.json");
      const privateSources = await read(recipient, `/projects/${project}/sources?query=FIN-12`);
      assert.deepEqual(privateSources.items, []);
      const beforeApproval = await read(recipient, `/projects/${project}/versions`);
      assert.deepEqual(beforeApproval.items, []);
      const approvalEvidence = await read(reviewer, `/projects/${project}/sources?query=M-07`);
      assert.ok(approvalEvidence.items.some((item) => item.original_id === "M-07"));
    }
    await reviewer
      .getByRole("textbox", { name: "Search permitted sources" })
      .fill(searchSource);
    await reviewer.getByRole("button", { name: "Search", exact: true }).click();
    await reviewer.getByRole("button", { name: new RegExp(searchSource) }).click();
    if (wala) {
      await reviewer.getByText(/Manually provided summary.*Original source not independently checked/).waitFor();
      await reviewer.getByRole("button", { name: "Check public GitHub issue" }).click();
      await reviewer.getByText("Retrieved from the official GitHub API", { exact: true }).waitFor();
      await capture(reviewer, "wala-public-snapshot");
    } else await reviewer.getByText(/Friday deployment was proposed/).waitFor();
    console.log("PASS authorized source exploration");

    if (full) {
      if (!personal) await uploadEvidence(reviewer, "issues.json");
      console.log("PASS synthetic import via Celery");

      await nav(reviewer, "AI Workflow").click();
      let jobId = existingJob;
      if (jobId) {
        const url = new URL(reviewer.url());
        url.searchParams.set("job", jobId);
        await reviewer.goto(url.href);
      } else {
        await reviewer
          .getByLabel("Handover task")
          .fill(task);
        await reviewer
          .getByRole("checkbox", { name: recipientEmail })
          .check();
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
      if (process.env.LLM_PROVIDER === "gemini" && process.env.LLM_MODEL) {
        const runs = await read(reviewer, `/jobs/${jobId}/runs`);
        assert.ok(runs.some((run) => run.status === "succeeded" && run.model === process.env.LLM_MODEL), "The configured Gemini model did not complete a stage");
      }
      await capture(reviewer, "workflow");
      const creatingDraft = watch(reviewer, "/drafts", "POST");
      await reviewer.getByRole("button", { name: "Open review draft" }).click();
      const draftResponse = await creatingDraft;
      if (existingJob && draftResponse.status() === 409) {
        await reviewer
          .getByRole("alert")
          .getByText("A draft already exists for this job")
          .waitFor();
        await reviewer
          .getByRole("button", { name: "Open review queue" })
          .click();
        await reviewer
          .getByRole("button", {
            name: new RegExp(task),
          })
          .first()
          .click();
      } else {
        assert.ok(
          draftResponse.ok(),
          "Create draft HTTP " + draftResponse.status(),
        );
      }
      const form = reviewer.locator("form").filter({
        has: reviewer.getByRole("heading", { name: "Critical-gap review" }),
      });
      await form.waitFor();
      const draftId = new URL(reviewer.url()).searchParams.get("draft");
      let draft = await read(reviewer, "/drafts/" + draftId);
      assert.equal(draft.agent_job_id, jobId);
      assert.deepEqual(draft.source_snapshot.map((item) => item.revision_id), draft.source_revision_ids);
      if (wala) {
        assert.deepEqual(draft.claims.map(({ claim }) => claim.kind), ["overview", "work_item", "work_item", "blocker"]);
        assert.ok(draft.claims[3].claim.statement.includes("#2121"));
        assert.ok(draft.unresolved.some((item) => item.includes("does not identify a confirmed human owner")));
      }
      let supporting;
      let subject;
      for (const { claim } of draft.claims) {
        const tree = await read(
          reviewer,
          "/claims/" + claim.id + "/tree?limit=100",
        );
        supporting = tree.branches.find(
          (branch) => branch.evidence?.relation === "supports",
        )?.evidence;
        if (supporting) {
          subject = claim;
          break;
        }
      }
      assert.ok(subject && supporting);
      const original = reviewer.locator("article").filter({
        has: reviewer.getByRole("heading", {
          name: subject.statement,
          exact: true,
        }),
      });
      await original.getByRole("button", { name: "Inspect evidence" }).click();
      await reviewer.locator(".evidence-column .claim-root").waitFor();
      assert.ok(await reviewer.locator(".evidence-column .tree li").count());
      const diagram = reviewer.locator(".evidence-diagram");
      if (await reviewer.locator(".evidence-column .tree li").count()) {
        await diagram.locator('.react-flow__node.source-node').first().click();
        await diagram.locator(".evidence-particle").first().waitFor();
        await capture(reviewer, "evidence-diagram");
        await reviewer.getByRole("button", { name: "Collapse branches" }).click();
        assert.equal(await diagram.locator(".react-flow__node").count(), 1);
        await reviewer.getByRole("button", { name: "Expand branches" }).click();
      }
      await original.getByRole("button", { name: "Explore Evidence", exact: true }).click();
      const explorer = reviewer.getByRole("dialog", { name: "Evidence Explorer" });
      const canvas = explorer.locator(".evidence-diagram");
      const sourceNode = canvas.locator(".source-node").first();
      if (wala) await sourceNode.getByText("GitHub Issue #2119", { exact: true }).waitFor();
      await sourceNode.click();
      await canvas.locator(".evidence-particle").first().waitFor();
      await explorer.getByRole("complementary", { name: "Selected node details" }).locator(".citation").first().waitFor();
      await canvas.locator(".react-flow__controls-zoomin").click();
      await canvas.locator(".react-flow__controls-zoomout").click();
      await canvas.locator(".react-flow__controls-fitview").click();
      await capture(reviewer, "evidence-explorer");
      if (wala) {
        assert.ok(await canvas.locator(".react-flow__node").evaluateAll((nodes) => {
          const boxes = nodes.map((node) => node.getBoundingClientRect());
          return boxes.every((a, index) => boxes.slice(index + 1).every((b) =>
            a.right <= b.left || b.right <= a.left || a.bottom <= b.top || b.bottom <= a.top));
        }));
        const pane = await canvas.locator(".react-flow__pane").boundingBox();
        const viewport = canvas.locator(".react-flow__viewport");
        const previous = await viewport.evaluate((node) => node.style.transform);
        await reviewer.mouse.move(pane.x + pane.width - 24, pane.y + pane.height - 24);
        await reviewer.mouse.down();
        await reviewer.mouse.move(pane.x + pane.width - 85, pane.y + pane.height - 55, { steps: 5 });
        await reviewer.mouse.up();
        assert.notEqual(await viewport.evaluate((node) => node.style.transform), previous);
        await canvas.locator(".react-flow__controls-fitview").click();
        await reviewer.emulateMedia({ reducedMotion: "reduce" });
        await canvas.locator(".evidence-particle").first().waitFor({ state: "hidden" });
        await reviewer.emulateMedia({ reducedMotion: "no-preference" });
        for (const [width, height] of [[1280, 800], [768, 1024], [390, 844]]) {
          await reviewer.setViewportSize({ width, height });
          await canvas.locator(".react-flow__controls-fitview").click();
          await reviewer.waitForFunction(() => {
            const diagram = document.querySelector(".evidence-workbench .evidence-diagram");
            if (!diagram) return false;
            const bounds = diagram.getBoundingClientRect();
            const nodes = [...diagram.querySelectorAll(".react-flow__node")];
            return nodes.length > 1 && nodes.every((node) => {
              const card = node.getBoundingClientRect();
              return card.left >= bounds.left - 1 && card.right <= bounds.right + 1 && card.top >= bounds.top - 1 && card.bottom <= bounds.bottom + 1;
            });
          });
          assert.ok(await explorer.evaluate((element) => element.scrollWidth <= element.clientWidth + 1), `Evidence Explorer overflow at ${width}`);
          await capture(reviewer, `wala-explorer-${width}`);
        }
        await reviewer.setViewportSize({ width: 1440, height: 900 });
      }
      await explorer.getByRole("button", { name: "Close explorer" }).click();
      await original.getByRole("button", { name: "Correct claim" }).click();
      await original
        .getByRole("textbox", { name: "Reason for correction" })
        .fill(
          "Verified and re-entered an exact citation for the synthetic claim.",
        );
      await original
        .getByRole("checkbox", {
          name: `${supporting.original_id} · supports · ${supporting.excerpt}`,
          exact: true,
        })
        .uncheck();
      await original
        .getByRole("checkbox", {
          name: "Add supporting citation from the draft snapshot",
        })
        .check();
      await original
        .getByLabel("Supporting evidence")
        .selectOption(supporting.revision_id);
      await original
        .getByLabel("Exact supporting quote")
        .fill(supporting.excerpt);
      const patched = reviewer.waitForResponse(
        (item) =>
          item.url().includes("/claims/") &&
          item.request().method() === "PATCH",
      );
      await original.getByRole("button", { name: "Save correction" }).click();
      assert.equal((await patched).status(), 200);
      await reviewer
        .getByText(new RegExp("^Draft revision " + (draft.revision + 1) + " ·"))
        .waitFor();
      draft = await read(reviewer, "/drafts/" + draftId);
      assert.ok(draft.claims.find(({ claim }) => claim.id === subject.id).flags.includes("semantic_review_required"));
      await capture(reviewer, "corrected-claim");
      for (const [index, { claim }] of draft.claims.entries()) {
        const field = form.locator("fieldset").nth(index);
        const critical = ["blocker", "prerequisite"].includes(claim.kind);
        await field
          .getByLabel("Classification")
          .selectOption(critical ? claim.kind : "non_critical");
        await field.getByLabel("Disposition").selectOption(critical ? (wala ? "blocking" : "unverified") : "non_blocking");
        await field
          .getByLabel("Rationale")
          .fill(
            wala ? "Reviewed against the imported dashboard summary and its limitations." : "Reviewed the claim snapshot. The separate approval gap tracks the missing testing sign-off.",
          );
      }
      if (!wala) {
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
        .getByLabel("Supporting evidence")
        .selectOption(approvalSource.revision_id);
      await gap
        .getByLabel("Rationale")
        .fill(
          "Monday approval requires testing sign-off, which is absent in the synthetic evidence.",
        );
      }
      const approve = form.getByRole("button", {
        name: "Approve immutable handover",
      });
      assert.equal(await approve.isDisabled(), true);
      await form
        .getByRole("checkbox", { name: /confirm the exact source/ })
        .check();
      await capture(reviewer, "review");
      const dialog = reviewer.getByRole("dialog", {
        name: "Publish this handover?",
      });
      await approve.focus();
      await reviewer.keyboard.press("Enter");
      await dialog.waitFor();
      await reviewer.keyboard.press("Escape");
      await dialog.waitFor({ state: "hidden" });
      const approving = watch(reviewer, "/approve", "POST");
      await approve.click();
      await reviewer
        .getByRole("dialog", { name: "Publish this handover?" })
        .getByRole("button", { name: "Publish version" })
        .click();
      const approval = await approving;
      assert.ok(approval.ok(), "Approval HTTP " + approval.status());
      const version = await approval.json();
      await reviewer
        .getByRole("heading", { name: "Approved handover" })
        .waitFor();
      await reviewer
        .getByRole("status")
        .getByText("Handover version published.")
        .waitFor();
      console.log(
        "PASS five agents, Evidence Tree, claim correction, critical-gap confirmation and immutable approval",
      );

      await nav(recipient, "Handover Versions").click();
      await recipient
        .getByRole("button", {
          name: new RegExp(task),
        })
        .first()
        .click();
      await recipient
        .getByRole("heading", { name: "Handover claims" })
        .waitFor();
      const detail = new URL(recipient.url());
      assert.equal(detail.searchParams.get("version"), version.id);
      const claim =
        version.handover.claims.find((item) => item.kind === "decision") ??
        version.handover.claims[0];
      await recipient
        .getByRole("button", { name: claim.statement, exact: false })
        .click();
      await recipient.locator(".evidence-column .citation").first().waitFor();
      await nav(recipient, "Evidence").click();
      await recipient
        .getByRole("heading", { name: "Evidence explorer" })
        .waitFor();
      await recipient
        .getByRole("button", { name: "Choose another package", exact: false })
        .click();
      await recipient
        .getByRole("button", {
          name: new RegExp(task),
        })
        .first()
        .click();
      await recipient
        .getByRole("button", { name: claim.statement, exact: false })
        .click();
      await recipient.locator(".evidence-column .citation").first().waitFor();
      assert.equal(
        new URL(recipient.url()).searchParams.get("version"),
        version.id,
      );
      await recipient.goto(detail.toString());
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
