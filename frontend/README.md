# KnotDevt K0.1.0 frontend

The public site, login, and workspace are static Next.js pages. The browser talks directly to the existing FastAPI service. Authentication, workflow execution, source authorization, review, grading, and persistence stay in the backend.

## Run locally

1. Start the backend and Celery worker using the [backend setup](../backend/README.md). Confirm [API readiness](http://localhost:8080/health/ready).
2. Include the exact origin `http://localhost:5173` in the backend's local `ALLOWED_ORIGINS` JSON list. Keep `localhost` in both browser URLs so the existing HttpOnly cookie remains same-site.
3. From `frontend/`, run:

   ```powershell
   npm ci
   npm run dev
   ```

Open [KnotDevt](http://localhost:5173). Sign in with an existing account. The workspace header exposes the signed-in user's ID for workflows that require an explicit recipient UUID. No credentials are required to build or open the public site.

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
