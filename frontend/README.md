# KnotDevt K0.1.0 frontend

The public site, login, and workspace are static Next.js pages. The browser talks directly to the existing FastAPI service. Authentication, workflow execution, source authorization, review, grading, and persistence stay in the backend.

## Run locally

1. Start the backend and Celery worker using the [backend setup](../backend/README.md). Confirm [API readiness](http://localhost:8080/health/ready).
2. The backend allows `http://localhost:3000` by default. If you override `ALLOWED_ORIGINS`, include that exact origin. Keep `localhost` in both browser URLs so the existing HttpOnly cookie remains same-site.
3. From `frontend/`, run:

   ```powershell
   npm ci
   npm run dev
   ```

Open [KnotDevt](http://localhost:3000). Sign in or create a personal account. Use **Set up your workspace** to create a workspace and a project. With the project open, a workspace administrator can choose **Overview → Invite teammate**, select **Recipient**, and copy the private one-hour code. The recipient signs in with the invited email and enters the code under **Set up your workspace → Join project**. After they join, select their email in **AI Workflow**.

The public site and production build do not require credentials. For the optional demo, use the existing seeded identities and obtain the password privately from the presenter.

Run `node tests/onboarding.mjs` against the local services to exercise registration, setup, a guided import and invitation acceptance in Microsoft Edge. It writes synthetic accounts and projects to the running local application.

For the full browser workflow, set `KNOTDEVT_E2E_WRITE=1` and run `node --env-file=../.env tests/browser.mjs`. Set `KNOTDEVT_E2E_PERSONAL=1` as well to create an isolated synthetic workspace and two fresh accounts instead of using the demo project. This test imports evidence and runs the configured model provider. Set `KNOTDEVT_E2E_SCREENSHOTS` to an existing local directory to save captures.

If sign-in is unavailable, check `/health/ready` first. When Docker publishes PostgreSQL on an alternate port, both `DATABASE_URL` and `RUNTIME_DATABASE_URL` in the private root `.env` must match that port. Restart the API and any worker processes after changing the local URLs. Reuse the existing database and volume.

## Routes

- `/` is the animated public site. Login triggers an original blue SVG wipe.
- `/login` uses the existing session endpoint.
- `/app` uses query parameters to link to the workspace, project, source library, AI workflow, draft review, versions and readiness. This keeps individual resource IDs addressable in the static export. The Evidence Tree has a separate column on wide screens and stacks below the primary panel on smaller screens.

Reviewers inspect exact citation spans and confirm a classification, disposition, and rationale for each current claim revision and the full source snapshot. Corrections invalidate prior form confirmations. Recipients can view version-bound Context Trace, submit a readiness rehearsal, and acknowledge receipt. Assessment score and package status are displayed separately.

## Checks

```powershell
npm run typecheck
npm run lint
npm run build
npm run test:browser
```

The browser smoke test uses local Microsoft Edge by default. Set `KNOTDEVT_BROWSER` to another Playwright Chromium channel if needed. It checks desktop and mobile public navigation. With the existing local demo password configured, it also verifies authentication, role navigation and source discovery:

```powershell
node --env-file=../.env tests/browser.mjs
```

To test the full reviewer and recipient path against the existing synthetic **SoloOne Demo / College event payments** project, set `KNOTDEVT_E2E_WRITE=1` for that process. This imports the synthetic fixture and creates a workflow job, draft, approved handover, assessment, and receipt. It requires a working Celery worker, the demo password, and existing demo evidence. Set `KNOTDEVT_E2E_SCREENSHOTS` to a local output directory to capture browser evidence.

Set `KNOTDEVT_E2E_JOB` to a completed job from this synthetic scenario to resume verification at the workflow review checkpoint without another model call.

To refresh generated TypeScript contracts after a backend schema change, run `npm run api:types` with the API running on port 8080. The production build exports files to `out/`.
