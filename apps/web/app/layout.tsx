import type { Metadata } from "next";
import { IBM_Plex_Mono, Instrument_Serif, Source_Sans_3 } from "next/font/google";

import { Providers } from "./providers";
import "./globals.css";

/**
 * Three faces, each with one job.
 *
 * The scaffold shipped Geist and Geist Mono, which are the `create-next-app` defaults and read as
 * exactly that -- the app looked generated because, typographically, it was. What this screen
 * actually resembles is a printed timetable: a roster, a set of departure times, a destination.
 * So it is set like one.
 *
 * `Instrument Serif` carries the display line -- page titles, section headings, a driver's name,
 * the figures in the result summary. It ships one weight and an italic, which is the right
 * constraint for display type: hierarchy comes from size and spacing rather than from six weights.
 * `Source Sans 3` is the text face, and does everything a reader's eye moves through quickly --
 * body, labels, controls, table rows. `IBM Plex Mono` is reserved for machine handles, where a
 * reader compares characters rather than reading words.
 *
 * Times are deliberately NOT mono: they are set in the text face with `tabular-nums`, which is
 * what a timetable does. Lining tabular figures align in a column without the typewriter texture.
 */
const display = Instrument_Serif({
  variable: "--font-display",
  subsets: ["latin"],
  weight: "400",
  style: ["normal", "italic"],
});
const text = Source_Sans_3({ variable: "--font-text", subsets: ["latin"] });
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
    <html
      lang="en"
      className={`${display.variable} ${text.variable} ${mono.variable} h-full antialiased`}
    >
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
