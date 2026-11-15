import assert from 'node:assert/strict';
import { chromium } from 'playwright';

let input = '';
for await (const chunk of process.stdin) input += chunk;
const config = JSON.parse(input);
const browser = await chromium.launch({ channel: 'msedge' });
try {
  const page = await browser.newPage();
  // Transparent forwarding to the real isolated API; no response fixtures.
  if (!config.direct) await page.route('**/api/v1/**', async route => {
    const url = new URL(route.request().url());
    const response = await route.fetch({ url: config.api + url.pathname + url.search });
    await route.fulfill({ response });
  });
  await page.goto(config.site + '/login');
  await page.locator('input[name=email]').fill(config.email);
  await page.locator('input[name=password]').fill(config.password);
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await page.waitForURL('**/app');
  await page.goto(config.site + `/app?workspace=${config.workspace}&project=${config.project}&view=agents`);
  await page.locator('input[name=task]').fill('Prepare the event-registration payment release');
  await page.locator('input[name=audience]').first().check();
  await page.getByRole('button', { name: 'Run workflow', exact: true }).click();
  await page.getByText('Human review checkpoint', { exact: true }).waitFor({ timeout: 45000 });
  const job = new URL(page.url()).searchParams.get('job');
  const stages = await page.locator('.agent-list > li > .flow > .row.spread > .badge').allTextContents();
  assert.equal(stages.length, 5);
  assert.ok(stages.every(stage => stage.trim() === 'succeeded'));
  if (config.screenshot) await page.screenshot({ path: config.screenshot, fullPage: true });
  await page.getByRole('button', { name: 'Open review draft', exact: true }).click();
  await page.getByRole('heading', { name: 'Critical-gap review', exact: true }).waitFor();
  const draft = new URL(page.url()).searchParams.get('draft');
  assert.ok(job && draft);
  console.log(JSON.stringify({ job, draft, stages, human_review: true }));
} finally { await browser.close(); }
