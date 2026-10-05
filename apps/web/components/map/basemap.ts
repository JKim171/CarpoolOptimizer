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

/**
 * `positron`, not `liberty`.
 *
 * Liberty is a full-colour general-purpose basemap -- green parkland, blue water, coloured road
 * classes -- and it was competing with the only thing on the map that carries information here:
 * the eight route colours in `lib/results/colors.ts`. At a thumbnail that was tolerable. Now that
 * the map runs the full width of the window it is the loudest element on the page, and it is
 * loudest about the parts that mean nothing.
 *
 * Positron is the desaturated grey basemap that newspapers and data graphics use, for exactly this
 * reason: it is a ground for marks to sit on. It also suits a page set like a printed document,
 * where a map is a plate.
 *
 * It stays light in both themes, deliberately. The route palette is documented as chosen to be
 * legible *on a light basemap*, and a dark ground would need a second palette of eight colours
 * re-picked against it. OpenFreeMap does serve `dark`, so that remains open -- it is a palette
 * decision, not a tile-source one.
 */
export const STYLE = "https://tiles.openfreemap.org/styles/positron";

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
