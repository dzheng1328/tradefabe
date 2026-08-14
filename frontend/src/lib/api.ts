// Shared fetch helper for the dashboard API. Every research-lab component used to do a
// bare `fetch(...).then(res => res.json())` with no `res.ok` check -- an error-shaped JSON
// body (e.g. `{detail: "..."}` instead of the expected shape) then caused a render-time
// TypeError that unmounted the whole page (no ErrorBoundary anywhere in this app). Route
// every fetch through this so a failed request throws a descriptive Error the caller can
// `.catch()` into a local error-message state instead.

export async function fetchJSON<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`fetch failed: ${res.status} ${url}`);
  }
  return res.json() as Promise<T>;
}
