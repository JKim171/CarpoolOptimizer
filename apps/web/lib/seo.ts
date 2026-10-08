/**
 * What this site says about itself to crawlers, and which of its paths are private.
 *
 * One module because three separate mechanisms have to agree on the same answer, and they are
 * declared in three different files that cannot import each other's intent: `app/robots.ts`
 * (what crawlers are told), `next.config.ts` (the `X-Robots-Tag` header), and
 * `components/analytics/WebAnalytics.tsx` (which page views are allowed to leave the origin).
 * A path that is private for one of those reasons is private for all three, so the predicate
 * lives here and all three call it.
 */

/**
 * The canonical origin, hard-coded rather than read from the environment.
 *
 * It is a published fact about a deployed site, not configuration: the apex 308s to this host, so
 * there is exactly one spelling of every URL. Reading it from `NEXT_PUBLIC_SITE_URL` would mean a
 * preview deployment could emit `<link rel="canonical">` pointing at itself and ask Google to index
 * a preview, which is the failure this constant exists to make impossible.
 */
export const SITE_URL = "https://www.whodriveswho.com";

/** Human-readable name, used for the wordmark in link previews. */
export const SITE_NAME = "whodriveswho";

/**
 * Event pages are private, and that is a privacy requirement rather than a preference.
 *
 * The URL carries the event's `public_id`, and the page itself renders participants' names and home
 * addresses for groups that may include minors (CLAUDE.md, docs/design.md 2). So an event URL must
 * not reach a search index and must not reach an analytics provider -- not the path, not the id in
 * it.
 *
 * Matching is exact-or-child, never `startsWith("/events")` alone: a future public page at
 * `/events-explained` would otherwise be silently excluded from both the sitemap and the analytics
 * it is supposed to be measured by, and nothing would report the mistake.
 */
export const PRIVATE_PATH_PREFIX = "/events";

export function isPrivatePath(pathname: string): boolean {
  return pathname === PRIVATE_PATH_PREFIX || pathname.startsWith(`${PRIVATE_PATH_PREFIX}/`);
}
