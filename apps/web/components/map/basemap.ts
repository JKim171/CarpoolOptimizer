/**
 * Shared basemap setup. Imported for its side effect by every component that builds a map.
 *
 * Tiles are OpenFreeMap. MapLibre is a renderer, not a tile source (docs/design.md 7.5), so a
 * source had to be chosen: OpenFreeMap needs no key and no account, which keeps the "no credential
 * ever reaches the browser" property the rest of this design depends on. MapTiler and Stadia both
 * want a key that would either ship in the bundle or need a second proxy.
 *
 * Attribution is not decoration -- OpenFreeMap serves OpenStreetMap data and the licence requires
 * crediting it -- so every map here passes `attributionControl`.
 */

import { setWorkerUrl } from "maplibre-gl";

import type { ColorScheme } from "@/lib/colorScheme";

/**
 * `positron` and `dark`, not `liberty`.
 *
 * Liberty is a full-colour general-purpose basemap -- green parkland, blue water, coloured road
 * classes -- and it was competing with the only thing on the map that carries information here:
 * the eight route colours in `lib/results/colors.ts`. At a thumbnail that was tolerable. Now that
 * the map is the canvas the whole app is laid out around, it is the loudest element on the screen,
 * and it was loudest about the parts that mean nothing.
 *
 * Positron is the desaturated grey basemap that newspapers and data graphics use, for exactly this
 * reason: it is a ground for marks to sit on. `dark` is the same idea on the other side -- a
 * near-black ground, `rgb(12,12,12)`, with grey road casings.
 *
 * **The map used to stay light in both themes**, because the route palette was chosen against a
 * light ground and a dark one needed a second set of eight colours picked against it. That set now
 * exists (`lib/results/colors.ts`), which is what made this switchable: it was always a palette
 * decision rather than a tile-source one. A light plate was tolerable while the map was a rectangle
 * in a document; filling most of a dark window, it was the design.
 */
const STYLES = {
  light: "https://tiles.openfreemap.org/styles/positron",
  dark: "https://tiles.openfreemap.org/styles/dark",
} as const;

export function styleFor(scheme: ColorScheme): string {
  return STYLES[scheme];
}

/** Ann Arbor, until something real recentres the view. */
export const FALLBACK_CENTER: [number, number] = [-83.743, 42.2808];

/**
 * Point MapLibre at the worker copied into `public/` by `scripts/copy-maplibre-worker.mjs`.
 *
 * Without this the worker request resolves through `import.meta.url` to something Turbopack never
 * emitted, Next answers with its HTML 404 page, and the browser rejects it for its MIME type. No
 * tile is then decoded, while the style and sprites -- fetched on the main thread -- load fine, so
 * the map is a correctly sized blank rectangle and MapLibre reports no error of its own.
 *
 * Set here rather than in each component so a third map cannot be added without it.
 */
setWorkerUrl("/maplibre/maplibre-gl-worker.mjs");
