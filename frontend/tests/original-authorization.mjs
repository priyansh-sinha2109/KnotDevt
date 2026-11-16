import assert from 'node:assert/strict';
import { chromium } from 'playwright';
let input = '';
for await (const chunk of process.stdin) input += chunk;
const config = JSON.parse(input);
const browser = await chromium.launch({ channel: 'msedge' });
try {
  const page = await browser.newPage();
  const apis = new Set();
  page.on('request', request => {
    if (request.url().includes('/api/v1/')) apis.add(new URL(request.url()).origin);
  });
  await page.goto('http://localhost:3000/login');
  await page.locator('input[name=email]').fill(config.email);
  await page.locator('input[name=password]').fill(config.password);
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await page.waitForURL('**/app');
  await page.goto(`http://localhost:3000/app?workspace=${config.workspace}&project=${config.project}&view=agents`);
  await page.locator('input[name=task]').fill('Authorization-gated synthetic handover');
  await page.locator('input[name=audience]').first().check();
  const accepted = page.waitForResponse(response => response.url().endsWith('/agent-jobs') && response.request().method() === 'POST');
  await page.getByRole('button', { name: 'Run workflow', exact: true }).click();
  const response = await accepted;
  assert.equal(response.status(), 202);
  const job = await response.json();
  assert.equal(job.phase, 'awaiting_provider_authorization');
  await page.getByText(/Awaiting AI provider authorization\. Your job is saved/).waitFor();
  const badges = await page.locator('.agent-list > li > .flow > .row.spread > .badge').allTextContents();
  assert.equal(badges.length, 5);
  assert.ok(badges.every(value => value.trim() === 'awaiting provider authorization'));
  assert.deepEqual([...apis], ['http://localhost:8080']);
  if (config.screenshot) await page.screenshot({ path: config.screenshot, fullPage: true });
  console.log(JSON.stringify({ job: job.id, phase: job.phase, apis: [...apis], stageBadges: badges }));
} finally { await browser.close(); }
