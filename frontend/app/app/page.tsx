import { Suspense } from "react";
import Workspace from "../../src/workspace";

export default function AppPage() {
  return (
    <Suspense
      fallback={<main className="app-loading">Opening workspace…</main>}
    >
      <Workspace />
    </Suspense>
  );
}
