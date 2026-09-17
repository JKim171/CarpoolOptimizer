/**
 * Organizer tokens, held per event in localStorage.
 *
 * An organizer token is a 90-day bearer credential granting full read/write access to one event --
 * including every participant's home address, for groups that may include minors. Keeping it in
 * localStorage is a deliberate tradeoff, not an oversight: the API lives on a different origin to
 * this app, so a cookie would have to be cross-site, and the alternative of holding it in memory
 * only means the organizer re-pastes it after every reload, in the middle of an event.
 *
 * What makes the tradeoff acceptable:
 *  - the token is scoped to a single event, so a leak is not an account compromise;
 *  - it expires in 90 days rather than never;
 *  - nothing on this origin renders untrusted HTML, and the CSP forbids inline and third-party
 *    script, which is what an XSS would need.
 *
 * Storage is keyed by event so that an organizer running two events does not silently authenticate
 * one with the other's token -- which the API answers with 401 rather than 404, making it look like
 * the event does not exist (docs/design.md 6.1).
 */

const PREFIX = "carpool.organizer.";

const keyFor = (publicId: string) => `${PREFIX}${publicId}`;

/** Server-render passes through here too, where there is no `window`. */
const storage = (): Storage | null => {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage;
  } catch {
    // Safari in private mode, and any browser with site data blocked, throws on access rather
    // than returning null. The app has to stay usable: the organizer re-pastes their token.
    return null;
  }
};

export function readToken(publicId: string): string | null {
  return storage()?.getItem(keyFor(publicId)) ?? null;
}

export function writeToken(publicId: string, token: string): void {
  storage()?.setItem(keyFor(publicId), token);
  forgetKnownEventsCache();
}

export function forgetToken(publicId: string): void {
  storage()?.removeItem(keyFor(publicId));
  forgetKnownEventsCache();
}

/** Every event this browser holds a token for, for the "your events" list on the home screen. */
export function knownEventIds(): string[] {
  const store = storage();
  if (!store) return [];
  const ids: string[] = [];
  for (let i = 0; i < store.length; i += 1) {
    const key = store.key(i);
    if (key?.startsWith(PREFIX)) ids.push(key.slice(PREFIX.length));
  }
  return ids;
}

/**
 * `useSyncExternalStore` plumbing for that list.
 *
 * localStorage does not exist while rendering on the server, so the list cannot simply be read
 * during render -- and reading it in an effect means a setState that React now warns about. This is
 * the shape React actually wants for "state that lives outside React": a server snapshot of empty,
 * a cached client snapshot, and invalidation when another tab writes a token.
 */
const NONE: string[] = [];
let snapshot: string[] | null = null;
const listeners = new Set<() => void>();

export function subscribeToKnownEvents(onChange: () => void): () => void {
  listeners.add(onChange);
  // `storage` fires only in *other* tabs, which is exactly the case this listener is for. Writes in
  // this tab notify through `forgetKnownEventsCache` below.
  window.addEventListener("storage", forgetKnownEventsCache);
  return () => {
    listeners.delete(onChange);
    window.removeEventListener("storage", forgetKnownEventsCache);
  };
}

export function knownEventsSnapshot(): string[] {
  // The snapshot must be a stable reference between changes: returning a fresh array every call
  // makes `useSyncExternalStore` re-render forever.
  snapshot ??= knownEventIds();
  return snapshot;
}

export function knownEventsServerSnapshot(): string[] {
  return NONE;
}

/**
 * Drop the cached list and tell React about it.
 *
 * Invalidating without notifying is a silent no-op: `useSyncExternalStore` only re-reads when a
 * subscriber fires, so a token written or forgotten in *this* tab would not reach the screen until
 * something else happened to re-render.
 */
export function forgetKnownEventsCache(): void {
  snapshot = null;
  for (const listener of listeners) listener();
}
