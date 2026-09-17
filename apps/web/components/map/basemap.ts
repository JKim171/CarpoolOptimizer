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

export const STYLE = "https://tiles.openfreemap.org/styles/liberty";

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
