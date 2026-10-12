/**
 * Record each basemap's layer ids and types, for `components/map/palette.test.ts` to check the
 * repaint table against.
 *
 * `components/map/palette.ts` names about fifty layers belonging to someone else's stylesheet, and
 * `setPaintProperty` **throws** when a property does not belong to the layer's type. That call runs
 * inside `style.load`, before the route layer is added -- so one wrong pair does not mis-tint one
 * plane, it takes down the whole canvas: no routes, no markers, no fit. That happened once
 * (`aeroway-runway` is a line in `dark`, and was filed as a fill), which is why both a type guard
 * and this snapshot exist.
 *
 * The test has to be offline and deterministic like every other one here, so it reads this file
 * rather than the network. That means the snapshot catches **our** mistakes -- a typo, a wrong
 * type -- and not an upstream rename, which only a refresh reveals. Run `npm run basemap:layers`
 * after changing the table or when OpenFreeMap ships a new style, and commit the result.
 *
 * Only ids and types are stored. The colours stay in `palette.ts`, where they are chosen.
 */

import { writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

// Kept in step with `components/map/basemap.ts`, which is where the app reads them from.
const STYLES = {
  light: "https://tiles.openfreemap.org/styles/positron",
  dark: "https://tiles.openfreemap.org/styles/dark",
};

const snapshot = {};
for (const [scheme, url] of Object.entries(STYLES)) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${url} -> ${response.status}`);
  const style = await response.json();
  snapshot[scheme] = Object.fromEntries(style.layers.map((layer) => [layer.id, layer.type]));
}

const out = join(
  dirname(fileURLToPath(import.meta.url)),
  "..",
  "components",
  "map",
  "basemapLayers.json",
);
await writeFile(out, `${JSON.stringify(snapshot, null, 2)}\n`);
console.log(
  `basemap layers -> components/map/basemapLayers.json ` +
    `(${Object.entries(snapshot)
      .map(([scheme, layers]) => `${scheme}: ${Object.keys(layers).length}`)
      .join(", ")})`,
);
