/**
 * The repaint table has to agree with the stylesheets it is repainting.
 *
 * `palette.ts` names about fifty layers in two basemaps this project does not own, and
 * `setPaintProperty` throws when the property does not belong to the layer's type. It is called
 * from `style.load`, *before* the route layer is added and before `ready` flips -- so a wrong pair
 * is not a mis-tinted plane, it is a map with no routes, no markers and no fit. That is exactly
 * what happened once: `aeroway-runway` is a line in `dark` and was filed as a fill, and the whole
 * canvas went with it.
 *
 * `applyMapPalette` now skips a mismatch instead of throwing, so the same mistake would be quiet
 * rather than fatal -- which is the right behaviour at runtime and the wrong one to leave
 * unchecked. This is the check: the real function, driven against a snapshot of the real styles
 * (`basemapLayers.json`, refreshed by `npm run basemap:layers`), asserting that every layer the
 * table names is one that exists and one that actually takes the paint.
 *
 * Same guard the dark palette gets from `app/globals.test.ts` and the API contract gets from
 * `test_openapi_contract.py`: stated as an invariant the build enforces rather than as a comment.
 */

import type { Map as MapLibreMap } from "maplibre-gl";
import { describe, expect, it } from "vitest";

import type { ColorScheme } from "@/lib/colorScheme";

// Relative, like `lib/demo/event.ts` imports its generated JSON: the `@/` alias is a tsconfig path
// and resolves for modules, not for a JSON asset under vitest.
import layers from "./basemapLayers.json";
import { GROUND_COLOR, applyMapPalette } from "./palette";

/**
 * Run the real function against a style that exists only as a table of ids and types, recording
 * what it asked for and what it painted. A stub rather than a mock of MapLibre: the two methods
 * below are the entire surface `applyMapPalette` touches, and a stub that drifts from that is a
 * compile error at the cast.
 */
function repaint(scheme: ColorScheme) {
  const types: Record<string, string> = layers[scheme];
  const named = new Set<string>();
  const painted = new Map<string, string[]>();

  const stub = {
    getLayer: (id: string) => {
      named.add(id);
      return types[id] ? { id, type: types[id] } : undefined;
    },
    setPaintProperty: (id: string, property: string) => {
      painted.set(id, [...(painted.get(id) ?? []), property]);
    },
  };

  applyMapPalette(stub as unknown as MapLibreMap, scheme);
  return { named, painted, types };
}

describe.each(["light", "dark"] as const)("the %s basemap repaint", (scheme) => {
  const { named, painted, types } = repaint(scheme);

  it("names only layers the style actually has", () => {
    const missing = [...named].filter((id) => !(id in types));
    expect(missing).toEqual([]);
  });

  it("paints every layer it names -- no property filed under the wrong layer type", () => {
    const skipped = [...named].filter((id) => !painted.has(id));
    expect(skipped).toEqual([]);
  });

  it("is not vacuously satisfied -- the table was read and the ground was painted", () => {
    // A table that failed to parse, or a function that returned early, would pass both checks
    // above with an empty set. Anchor on the one layer the whole point depends on.
    expect(named.size).toBeGreaterThan(5);
    expect(painted.get("background")).toEqual(["background-color"]);
    expect(GROUND_COLOR[scheme]).toMatch(/^#[0-9a-f]{6}$/);
  });
});
