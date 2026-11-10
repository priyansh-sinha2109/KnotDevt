# Frontend API configuration

Set `NEXT_PUBLIC_API_BASE_URL` before starting or building the Next.js frontend.
It is a public configuration value and must never contain credentials.
The default is `http://localhost:8080/api/v1`.

For hosting, prefer `/api/v1` with an HTTPS reverse proxy on the frontend
origin forwarding API requests and cookies to FastAPI. The static frontend
export does not provide this proxy; configure it in the hosting infrastructure.
Alternatively, use an HTTPS API subdomain on the same site and allow the exact
frontend origin in the backend CORS and trusted-origin configuration.

Keep credentialed requests, CSRF validation, HttpOnly cookies and secure cookies
enabled. Unrelated frontend and backend domains are cross-site: merely changing
this URL does not make the existing SameSite cookie architecture compatible.
Use a same-origin proxy or same-site domains rather than weakening cookie rules.

Next.js embeds public environment values at build time. Rebuild after changing
the API URL. No deployment has been performed or verified by this configuration.
