/**
 * Copy MapLibre's worker into `public/` so the browser can actually fetch it.
 *
 * MapLibre 6 parses vector tiles in a web worker, and resolves that worker through
 * `import.meta.url`. Turbopack does not emit the separate `maplibre-gl-worker.mjs` as a servable
 * asset, so the request falls through to Next's router and comes back as the HTML 404 page. The
 * browser refuses it ("non-JavaScript MIME type"), the worker never starts, and **no tile is ever
 * decoded** -- while the style, sprites and glyphs, which load on the main thread, all succeed. The
 * result is a correctly sized, completely blank map with no error from MapLibre at all.
 *
 * `setWorkerUrl` (called in `components/DestinationMap.tsx`) is MapLibre's supported escape hatch;
 * it needs a URL this app serves, which is what this produces.
 *
 * The obvious shortcut is to drop back to maplibre-gl 5.x, which inlines its worker and sidesteps
 * all of this. That is not available: the installed major is a security floor, not a preference.
 * Run `npm audit` before changing the maplibre version and the reason is immediate.
 *
 * Both files are copied because the worker imports `./maplibre-gl-shared.mjs` relatively, so they
 * have to stay side by side. The copies are build output: gitignored, and refreshed before every
 * dev run and build so they cannot drift from the installed version.
 */

import { copyFile, mkdir } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const from = join(here, "..", "node_modules", "maplibre-gl", "dist");
const to = join(here, "..", "public", "maplibre");

const FILES = ["maplibre-gl-worker.mjs", "maplibre-gl-shared.mjs"];

await mkdir(to, { recursive: true });
for (const file of FILES) {
  await copyFile(join(from, file), join(to, file));
}
console.log(`maplibre worker -> public/maplibre/ (${FILES.join(", ")})`);
