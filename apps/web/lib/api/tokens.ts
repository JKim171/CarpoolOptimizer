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
}

export function forgetToken(publicId: string): void {
  storage()?.removeItem(keyFor(publicId));
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
