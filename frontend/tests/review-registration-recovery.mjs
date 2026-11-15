import assert from 'node:assert/strict';
import { chromium } from 'playwright';

const browser = await chromium.launch({ channel: 'msedge' });
try {
  const page = await browser.newPage();
  let registrations = 0, logins = 0;
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname;
    let data = { items: [], next_offset: null }, status = 200;
    if (path.endsWith('/auth/register')) { registrations++; status = 204; }
    else if (path.endsWith('/auth/login')) { logins++; status = 503; data = { detail: 'Synthetic login outage' }; }
    else if (path.endsWith('/auth/me')) data = { email: 'test@example.invalid', csrf_token: 'test' };
    else if (path.endsWith('/workspaces')) data.items = [{ id: 'w', name: 'Synthetic', role: 'administrator' }];
    else if (path.endsWith('/projects')) data.items = [{ id: 'p', name: 'Recovery', role: 'reviewer' }];
    else if (path.endsWith('/drafts/d')) data = {
      id: 'd', project_id: 'p', revision: 1, task: 'Synthetic review',
      audience: [], unresolved: [], source_revision_ids: [], source_snapshot: [],
      proposed_rubric: { title: 'Synthetic rubric', questions: [] },
      claims: [{ claim: { id: 'c', revision_id: 'r', kind: 'overview', status: 'unverified', statement: 'Synthetic claim' }, flags: [] }],
    };
    await route.fulfill({ status, contentType: 'application/json', body: status === 204 ? '' : JSON.stringify(data) });
  });
  await page.goto('http://127.0.0.1:3005/login.html');
  await page.getByRole('button', { name: 'Create account', exact: true }).click();
  await page.locator('input[name=email]').fill('test@example.invalid');
  await page.locator('input[name=password]').fill('synthetic-only-password');
  await page.locator('form').getByRole('button', { name: 'Create account' }).click();
  await page.getByRole('alert').filter({ hasText: 'Your account was created' }).waitFor();
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await page.getByRole('alert').filter({ hasText: 'Synthetic login outage' }).waitFor();
  assert.equal(registrations, 1);
  assert.equal(logins, 2);
  console.log('PASS: successful registration then failed login recovers to sign-in without duplicate registration');
  await page.goto('http://127.0.0.1:3005/app.html?workspace=w&project=p&view=review&draft=d');
  const confirmation = page.getByRole('checkbox', { name: /I confirm the exact source snapshot/ });
  await confirmation.check();
  await page.locator('fieldset.gap-form select').first().selectOption('non_critical');
  assert.equal(await confirmation.isChecked(), false);
  await confirmation.check();
  await page.getByLabel('Rationale', { exact: true }).first().fill('Updated review rationale');
  assert.equal(await confirmation.isChecked(), false);
  await confirmation.check();
  await page.getByRole('button', { name: 'Add evidence-backed gap' }).click();
  assert.equal(await confirmation.isChecked(), false);
  await confirmation.check();
  await page.getByRole('button', { name: 'Remove gap' }).click();
  assert.equal(await confirmation.isChecked(), false);
  console.log('PASS: confirmation resets on classification, rationale, added gap, removed gap');
} finally { await browser.close(); }
