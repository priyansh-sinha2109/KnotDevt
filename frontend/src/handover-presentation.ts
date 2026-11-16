/** Read-only presentation helpers for source-derived records.
 *
 * Older source drafts stored the connector JSON beside the source id in the
 * claim statement.  The evidence remains valid, but never belongs in the
 * primary reviewer or recipient experience.
 */
export function isSourceRecord(statement: string) {
  const text = statement.trim();
  return /^ext-[a-f0-9-]+:\s*\{/.test(text) || /:\s*\{\s*"/.test(text);
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
  const prefix = statement.slice(0, statement.indexOf("{")).replace(/^ext-[a-f0-9-]+:\s*/, "").replace(/:\s*$/, "").trim();
  const detail = commitMessage ?? title ?? name ?? prefix ?? "Imported source record";
  const suffix = state && state !== detail ? ` · ${state}` : "";
  return `Recorded source activity: ${detail}${suffix}`;
}

export function sourceRecordDetail(statement: string) {
  if (!isSourceRecord(statement)) return "Evidence-linked project record";
  const source = value(statement, "full_name") ?? value(statement, "html_url");
  return source ? `Imported from ${source}` : "Imported source record";
}
