/**
 * Keeps event pages out of search indexes.
 *
 * This layout exists only to carry the metadata below. The page it wraps is a client component, and
 * a client component cannot export `metadata`, so there has to be a server component in the segment
 * to say this -- and this is the narrowest place that covers every event URL.
 *
 * The rule was previously in the root layout, where it was inherited by the landing page and made
 * the entire site unindexable. Narrowing it is what made the site indexable at all; re-stating it
 * here is what keeps that from being a privacy regression. The URL carries the event's `public_id`
 * and the page renders participants' names and home addresses, for groups that may include minors
 * (CLAUDE.md, docs/design.md 2).
 *
 * Two mechanisms say this, deliberately. `next.config.ts` sets `X-Robots-Tag` on the same paths, so
 * an edit that drops one still leaves the other standing. A single `noindex` guarding addresses is
 * one careless refactor away from gone, and nothing in the build would fail.
 */

import type { Metadata } from "next";

export const metadata: Metadata = {
  robots: { index: false, follow: false },
};

export default function EventLayout({ children }: LayoutProps<"/events/[publicId]">) {
  return children;
}
