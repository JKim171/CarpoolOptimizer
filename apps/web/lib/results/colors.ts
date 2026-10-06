/**
 * One colour per car, shared by the map and the list beside it.
 *
 * The colour is the only thing tying "Maya's car" in the list to a line on the map, so it has to be
 * assigned in one place. Read off the route's position in the solution, which is stable for as long
 * as a solution exists -- re-solving may recolour, and that is correct: it is a different answer.
 *
 * **There are two palettes, because there are two basemaps.** These colours sit on top of streets
 * and parkland rather than on the page, so the ground they are read against is the tile, not the
 * surface token. `positron` is a pale grey and wants dark, saturated marks; OpenFreeMap's `dark`
 * paints its background `rgb(12,12,12)` and wants light ones. A single palette cannot do both: the
 * light set's `#1d4ed8` is a smudge on near-black, and the dark set's `#fde047` is invisible on
 * paper. Both sets exclude the hue the destination marker uses, so the venue never reads as
 * somebody's car.
 */

import type { ColorScheme } from "@/lib/colorScheme";

/**
 * Chosen to stay legible on `positron`. Unchanged from when it was the only palette -- it was
 * verified against that ground and nothing about that ground has moved.
 */
const ROUTE_COLORS_LIGHT = [
  "#1d4ed8", // blue
  "#047857", // green
  "#b45309", // amber
  "#7c3aed", // violet
  "#0369a1", // sky
  "#a21caf", // fuchsia
  "#4d7c0f", // olive
  "#c2410c", // orange
] as const;

/**
 * Chosen against the dark basemap's `#0c0c0c` ground, and ordered so that *adjacent* cars are far
 * apart on the colour wheel -- car 1 and car 2 are the pair most often compared, and the eighth
 * colour is reached only on a roster that needs nine cars.
 *
 * Every entry clears 7:1 against the ground and 4:1 against the brightest road casing the style
 * paints (`rgba(60,60,60,.8)`), which is the worst case: a route line crossing a motorway. The
 * closest two hues are 23 degrees apart. The light palette above manages 15 degrees at its
 * closest (`#1d4ed8` against `#0369a1`), so this is the better-separated of the two; the light one
 * is left alone rather than re-picked because it is in production and works.
 */
const ROUTE_COLORS_DARK = [
  "#60a5fa", // blue
  "#fde047", // yellow
  "#34d399", // emerald
  "#e879f9", // fuchsia
  "#22d3ee", // cyan
  "#fb923c", // orange
  "#a3e635", // lime
  "#a78bfa", // violet
] as const;

/**
 * The venue. A square on the map too, so this is not the only thing distinguishing it.
 *
 * The dark value is a rose rather than a straight red: on near-black the palette needs a bright
 * orange, and a bright red sits only 20-odd degrees from it. Pushing the destination to 351 degrees
 * buys 36 degrees of separation while still reading unmistakably as "the marker that is not a car".
 */
const DESTINATION_COLORS = { light: "#991b1b", dark: "#fb7185" } as const;

export function destinationColor(scheme: ColorScheme): string {
  return DESTINATION_COLORS[scheme];
}

/**
 * Cars beyond the palette wrap around and share a colour. With a 50-person cap and a realistic
 * seat count that needs ~9 cars before it happens, and the list stays unambiguous when it does.
 */
export function routeColor(index: number, scheme: ColorScheme): string {
  const palette = scheme === "dark" ? ROUTE_COLORS_DARK : ROUTE_COLORS_LIGHT;
  return palette[index % palette.length];
}
