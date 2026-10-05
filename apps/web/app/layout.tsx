import type { Metadata } from "next";
import { IBM_Plex_Mono, Karla } from "next/font/google";

import { Providers } from "./providers";
import "./globals.css";

/**
 * One family, doing everything.
 *
 * The scaffold shipped Geist and Geist Mono -- the `create-next-app` defaults -- so the app looked
 * generated because, typographically, it was. The first attempt at a fix went the other way and
 * set the display line in `Instrument Serif`, a high-contrast display serif. That was too
 * mannered: hairline strokes at a heading size read as delicate rather than confident, and a
 * serif/sans split is a second system to keep in agreement for no benefit this app collects.
 *
 * `Karla` replaces both. It is a humanist sans with warmth in its letterforms and enough character
 * at large sizes to carry a heading without a second face -- so hierarchy comes from size and
 * weight alone, which is one decision instead of two. `IBM Plex Mono` stays, for machine handles
 * only, where a reader compares characters rather than reading words.
 *
 * Times are deliberately NOT mono: they are set in the text face with `tabular-nums`, which is
 * what a timetable does. Lining tabular figures align in a column without the typewriter texture.
 */
const sans = Karla({ variable: "--font-text", subsets: ["latin"] });
const mono = IBM_Plex_Mono({ variable: "--font-mono", subsets: ["latin"], weight: ["400", "500"] });

export const metadata: Metadata = {
  title: "CarpoolOptimizer",
  description: "Decide who drives whom, in what order, out and back.",
  // Event pages are reachable only with an organizer token, and their URLs carry a public id that
  // should not end up in a search index.
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${sans.variable} ${mono.variable} h-full antialiased`}>
      {/*
        `overflow-x-clip`, not `hidden`: the full-bleed map escapes the content column by the usual
        `left-1/2 w-screen -translate-x-1/2`, and `100vw` includes the scrollbar gutter, so without
        this the page gains a few pixels of horizontal scroll. `clip` suppresses that without
        making the body a scroll container, which `hidden` would -- and that would break `position:
        sticky` anywhere inside it.
      */}
      <body className="flex min-h-full flex-col overflow-x-clip">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
