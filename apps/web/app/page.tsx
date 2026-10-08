/**
 * The one public, indexable page on this site.
 *
 * It is a server component that renders a client one, for a single reason: `metadata` cannot be
 * exported from a client component, and this page needs to state its own canonical URL. Without one,
 * a link shared with tracking parameters -- `?utm_source=...` from a forum post, or a referrer tag a
 * site appends on its own -- can be indexed as a separate URL with the same content, splitting the
 * page's own ranking signals between spellings of it. The screen itself lives in `HomeDashboard`.
 */

import type { Metadata } from "next";

import { HomeDashboard } from "@/components/HomeDashboard";

export const metadata: Metadata = {
  // Relative, resolved against `metadataBase` in the root layout.
  alternates: { canonical: "/" },
};

export default function Home() {
  return <HomeDashboard />;
}
