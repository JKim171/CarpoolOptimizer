import type { Metadata } from "next";
import { IBM_Plex_Mono, Karla } from "next/font/google";

import { SITE_NAME, SITE_URL } from "@/lib/seo";

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

/**
 * Site-wide metadata. Public by default; private where it has to be.
 *
 * This used to carry `robots: { index: false, follow: false }`, reasoning about event pages -- which
 * was correct about event pages and wrong about where to say it. In the root layout it is inherited
 * by every route, so the landing page told Google to ignore it too, and the whole domain was
 * unindexable. The rule now lives in `app/events/[publicId]/layout.tsx`, next to the only pages it
 * is about, and is backed by an `X-Robots-Tag` header in `next.config.ts` so that losing one does
 * not expose an event URL.
 *
 * `metadataBase` is what makes the relative `canonical` on each page and the Open Graph URLs below
 * resolve to absolute ones.
 */
export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  // The brand reads as one word, lowercase, the way the domain does. The default title also says
  // what the thing is, because a search result showing only a coined word tells a reader nothing.
  title: {
    default: `${SITE_NAME} — work out who drives who`,
    template: `%s · ${SITE_NAME}`,
  },
  description:
    "A free tool for carpool coordinators. Enter a roster and get an assignment: who drives who, " +
    "in what pickup order, out and back. Built for teams, clubs and troops heading to one place " +
    "at one time.",
  applicationName: SITE_NAME,
  openGraph: {
    type: "website",
    siteName: SITE_NAME,
    url: "/",
    title: `${SITE_NAME} — work out who drives who`,
    description:
      "Enter a roster, get an assignment: who drives who, in what pickup order, out and back.",
    locale: "en_US",
  },
  // No Open Graph image yet, so a shared link renders as a title-and-description card rather than a
  // broken one. Worth adding before any public post -- see docs/handoff.md.
};

/**
 * Write the chosen theme onto `<html>` before anything paints.
 *
 * The OS preference needs no script -- `globals.css` answers it with a media query. A *chosen*
 * theme does, because it lives in localStorage, and it has to be read in a blocking script in the
 * document rather than in React: by the time an effect or even a hydration render could set the
 * attribute, the browser has already painted a screen using the other palette. That flash is the
 * whole reason this is here, and it is worst in the case people notice most -- someone who chose
 * light on a dark machine gets a dark flash on every single navigation.
 *
 * `system` deliberately writes nothing: no attribute is what lets the media query apply. Same rule
 * as `applyPreference` in `lib/colorScheme.ts`, which takes over once React is running; the two
 * have to agree, so each one's comment points at the other.
 *
 * `JSON.stringify` on the key is not decoration -- it is what keeps this a string literal rather
 * than something a future edit could turn into an injection point. Note that this inline script
 * means a Content-Security-Policy for this app cannot be `script-src 'self'` alone; it needs a
 * nonce or a hash for this one tag. There is no CSP on the web app today (the one `tokens.ts`
 * describes is not deployed), so this costs nothing now and is written down for whoever adds one.
 */
const THEME_SCRIPT = `try{var p=localStorage.getItem(${JSON.stringify(
  "carpool.theme",
)});if(p==="light"||p==="dark")document.documentElement.setAttribute("data-theme",p)}catch(e){}`;

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    // `suppressHydrationWarning` because the script above changes an attribute on this element
    // before React hydrates, which is exactly the mismatch the warning is for and exactly the
    // mismatch that is intended here. It suppresses one level deep -- this element only.
    <html
      lang="en"
      suppressHydrationWarning
      className={`${sans.variable} ${mono.variable} h-full antialiased`}
    >
      {/*
        The shell owns the viewport and scrolls its rail internally, so the document itself never
        scrolls. This used to be `flex min-h-full flex-col overflow-x-clip`, where the `clip` was
        load-bearing: a full-bleed map escaped the text column with `left-1/2 w-screen
        -translate-x-1/2`, and `100vw` includes the scrollbar gutter, which showed up as a few
        pixels of horizontal scroll. There is no text column to escape any more.
      */}
      <body className="h-full overflow-hidden">
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
