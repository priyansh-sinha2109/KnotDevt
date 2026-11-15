import assert from 'node:assert/strict';
import { chromium } from 'playwright';

const browser = await chromium.launch({ channel: 'msedge' });
try {
  const page = await browser.newPage();
  let calls = 0;
  let mode = 'temporary';
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname;
    let data = { items: [], next_offset: null };
    let status = 200;
    if (path.endsWith('/auth/me')) data = { email: 'synthetic@test.invalid', csrf_token: 'test', user_id: 'u' };
    else if (path.endsWith('/workspaces')) data.items = [{ id: 'w', name: 'Synthetic', role: 'administrator' }];
    else if (path.endsWith('/projects')) data.items = [{ id: 'p', workspace_id: 'w', name: 'Recovery', role: 'reviewer' }];
    else if (path.endsWith('/recipients') || path.endsWith('/runs')) data = [];
    else if (path.endsWith('/jobs/j')) {
      calls++;
      if (mode === 'timeout' && calls === 1) {
        await new Promise(resolve => setTimeout(resolve, 17000));
      }
      if (mode === 'network' && calls === 1) return route.abort('failed');
      if (mode === 'permanent') status = 403;
      else if (mode === 'exhausted' || (mode === 'temporary' && calls === 1)) status = 503;
      data = status === 200 ? { id: 'j', state: 'succeeded', phase: 'awaiting_human_review', revisions: [] } : { detail: 'Synthetic interruption' };
    }
    await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(data) });
  });
  const url = 'http://127.0.0.1:3005/app.html?workspace=w&project=p&view=agents&job=j';
  await page.goto(url);
  await page.getByText('Status check interrupted. Retrying automatically...').waitFor();
  await page.getByText('Human review checkpoint', { exact: true }).waitFor();
  assert.equal(calls, 2);
  await page.waitForTimeout(2500);
  assert.equal(calls, 2, 'terminal jobs must stop polling');
  mode = 'permanent'; calls = 0;
  await page.reload();
  await page.getByRole('button', { name: 'Retry status check' }).waitFor();
  await page.waitForTimeout(3000);
  assert.equal(calls, 1, '403 must not automatically retry');
  mode = 'recovered';
  await page.getByRole('button', { name: 'Retry status check' }).click();
  await page.getByText('Human review checkpoint', { exact: true }).waitFor();
  assert.equal(calls, 2);
  mode = 'temporary'; calls = 0;
  await page.reload();
  await page.getByRole('button', { name: 'Retry status check' }).waitFor();
  await page.getByRole('button', { name: 'Overview', exact: true }).click();
  await page.waitForTimeout(3500);
  assert.equal(calls, 1, 'navigation must cancel scheduled retries');
  for (const failure of ['network', 'timeout']) {
    mode = failure; calls = 0;
    await page.goto(url);
    await page.getByText('Status check interrupted. Retrying automatically...').waitFor();
    await page.getByText('Human review checkpoint', { exact: true }).waitFor();
    assert.equal(calls, 2, `${failure} must recover`);
  }
  await page.clock.install();
  mode = 'exhausted'; calls = 0;
  await page.goto(url);
  await page.getByRole('button', { name: 'Retry status check' }).waitFor();
  for (let i = 0; i < 7; i++) {
    await page.clock.fastForward(40000);
    await page.waitForTimeout(100);
  }
  assert.equal(calls, 6, 'five retries after the initial failure');
  await page.clock.fastForward(120000);
  assert.equal(calls, 6, 'exhausted polling must stop');
  mode = 'recovered';
  await page.getByRole('button', { name: 'Retry status check' }).click();
  await page.getByText('Human review checkpoint', { exact: true }).waitFor();
  console.log('PASS: exhausted retries stop and manual retry recovers');
  console.log('PASS: temporary 503 recovery; terminal stop; 403 stop; manual recovery; navigation cancellation; network disconnect recovery; request timeout recovery');
} finally { await browser.close(); }
