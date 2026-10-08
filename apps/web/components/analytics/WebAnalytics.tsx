"use client";

/**
 * Aggregate page views for the public pages, and nothing for the private ones.
 *
 * Vercel Web Analytics was chosen over the alternatives for what it does *not* do: it sets no cookie,
 * builds no cross-site profile, and records no session replay. That last one is disqualifying here
 * rather than merely undesirable -- a replay or DOM-capture product pointed at this app would ship
 * participants' names and home addresses to a third party as a matter of normal operation. Nothing of
 * that kind goes on this site, whatever it would tell us.
 *
 * A client component because `beforeSend` is a function, and a server component cannot pass one
 * across the boundary. The filter itself lives in `lib/analytics.ts` so it can be tested without
 * loading the provider.
 *
 * This renders a third-party script tag, which is the second thing on this origin that a future
 * Content-Security-Policy has to account for -- the other being the inline theme script in
 * `app/layout.tsx`. `script-src 'self'` alone would block this one outright; it needs Vercel's
 * analytics host. Worth knowing because `lib/api/tokens.ts` cites a CSP that does not exist yet as
 * part of why an organizer token may live in localStorage.
 *
 * The dashboard side has to be switched on in the Vercel project for any of this to record; the tag
 * is inert until it is.
 */

import { Analytics } from "@vercel/analytics/next";

import { allowPageView } from "@/lib/analytics";

export function WebAnalytics() {
  return <Analytics beforeSend={allowPageView} />;
}
