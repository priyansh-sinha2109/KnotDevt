/** Read-only presentation helpers for source-derived records.
 *
 * Older source drafts stored the connector JSON beside the source id in the
 * claim statement.  The evidence remains valid, but never belongs in the
 * primary reviewer or recipient experience.
 */
export function isSourceRecord(statement: string) {
  return /^ext-[a-f0-9-]+:\s*\{/.test(statement.trim());
}

function value(text: string, key: string) {
  const match = text.match(new RegExp(`"${key}"\\s*:\\s*"([^"\\n]+)"`));
  return match?.[1]?.replace(/\\n/g, " ").trim();
}

export function presentClaim(statement: string) {
  if (!isSourceRecord(statement)) return statement;
  const commitMessage = value(statement, "message");
  const title = value(statement, "title");
  const name = value(statement, "full_name") ?? value(statement, "name");
  const state = value(statement, "state");
  const detail = commitMessage ?? title ?? name ?? "Imported project record";
  const suffix = state && state !== detail ? ` · ${state}` : "";
  return `Recorded source activity: ${detail}${suffix}`;
}

export function sourceRecordDetail(statement: string) {
  if (!isSourceRecord(statement)) return "Evidence-linked project record";
  const source = value(statement, "full_name") ?? value(statement, "html_url");
  return source ? `Imported from ${source}` : "Imported source record";
}
