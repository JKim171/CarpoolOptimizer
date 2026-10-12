/**
 * The basemap, repainted into this app's palette.
 *
 * **Why the tiles need this at all.** The map is the canvas (`components/shell/AppShell.tsx`), so
 * the largest coloured area on every screen is a tile, not a token. OpenFreeMap's `dark` paints its
 * ground `rgb(12,12,12)` and `positron` paints its own `rgb(242,243,240)` -- a near-black and a
 * near-white, both neutral, and both at the far end of their range. The rest of this palette is
 * deliberately *not* at the extremes (`app/globals.css`): paper is an off-white and ink is a brown
 * near-black. Beside that, the light basemap read as the brightest thing on the screen and the dark
 * one read as a hole. The plane covering three quarters of the window has to agree with the rail
 * beside it -- after this the two differ by a contrast ratio of 1.03 in dark and 1.04 in light,
 * which is the same register rather than the same colour.
 *
 * **The light side is a ground shift; the dark side is a repaint.** Positron's roads and labels are
 * white and mid-grey on pale grey, and they sit on a warmer, slightly deeper ground without
 * argument -- that is what a printed map looks like. `dark` cannot be treated that way, because its
 * roads are painted *darker* than its ground: `highway_motorway_inner` is literally `#000`, read
 * against `#0c0c0c` as a hairline inside a grey casing. Lift the ground and leave that alone and
 * the motorway stops reading as a road and starts reading as a black river across the city. So on
 * the dark side the roads, railways, boundaries and label halos move with the ground, each keeping
 * the relationship to it that the style's author chose.
 *
 * **What it costs.** The route palettes in `lib/results/colors.ts` are picked against these
 * grounds. On the dark side every car was at 7.2:1 against `#0c0c0c` and is now at 6.2:1 against
 * `#1f1c16` at worst; on the light side the worst two drop from 4.5:1 to 4.1:1. These are 3.5px
 * lines and 14px pins rather than text, so the bar that applies is 3:1 -- but it is a real cost,
 * recorded here rather than discovered later, and it is why the ground moved one step and not
 * three. The marks are still far and away the loudest thing on the map: the brightest road reaches
 * 1.5:1 against the ground it sits on.
 *
 * Applied from every `style.load` handler, which fires for the first style and for each one a theme
 * change swaps in.
 */

import type { Map as MapLibreMap } from "maplibre-gl";

import type { ColorScheme } from "@/lib/colorScheme";

/**
 * The flat plane behind everything, per theme. Exported because a marker's ring has to approximate
 * the ground it sits on (`components/map/markers.ts`) -- one value, named once.
 */
export const GROUND_COLOR = { light: "#ece7dc", dark: "#1f1c16" } as const;

/**
 * The paint properties this file sets. Named as a union rather than taking `string`, so a typo in
 * the table is a build error instead of a MapLibre warning nobody reads -- and so that adding a
 * kind of property is a deliberate edit here.
 */
type PaintProperty =
  "background-color" | "fill-color" | "line-color" | "text-color" | "text-halo-color";

/** A paint patch applied to each of several layers that should look the same. */
type Group = [ids: string[], paint: Partial<Record<PaintProperty, string>>];

/**
 * An explicit table rather than a transform over the style's own values: the arithmetic that lifts
 * `rgb(12,12,12)` pleasantly turns parkland muddy, and a basemap is read, not computed.
 *
 * Layer ids come from the two styles as served. A missing one is skipped rather than thrown on --
 * these are someone else's stylesheets and they are free to rename a layer, in which case that one
 * plane keeps its shipped colour and the map is slightly inconsistent, not broken. Anything not
 * named here is left exactly as it ships.
 */
const PATCHES: Record<ColorScheme, Group[]> = {
  /**
   * Ground only. Positron's own marks already sit the right way round against it: roads lighter
   * than land, labels darker, which is the convention this ground was chosen to keep.
   */
  light: [
    [["background"], { "background-color": GROUND_COLOR.light }],
    [["road_area_pier"], { "fill-color": GROUND_COLOR.light }],
    [["water"], { "fill-color": "#c3c8c4" }],
    [["park"], { "fill-color": "#e3e2d2" }],
    [["landuse_residential"], { "fill-color": "#e5e0d4" }],
    [["landcover_wood"], { "fill-color": "#dfded0" }],
    [["building"], { "fill-color": "#e4ded0" }],
  ],

  dark: [
    [["background"], { "background-color": GROUND_COLOR.dark }],
    [["water"], { "fill-color": "#262520" }],
    // `dark` has no `park` layer; parkland comes through these two.
    [["landuse_park", "landcover_wood"], { "fill-color": "#2a2820" }],
    // A shade under the ground, the way the style has it: a residential block is a slight
    // darkening, not a plate.
    [["landuse_residential"], { "fill-color": "#1d1a15" }],
    [["building"], { "fill-color": "#1b1813" }],
    [["road_area_pier"], { "fill-color": GROUND_COLOR.dark }],

    // Roads, in the style's own order of importance: a motorway is the brightest thing, a minor
    // road barely separates from the ground, and the casing is what gives either an edge.
    [["highway_motorway_inner"], { "line-color": "#3d382e" }],
    [["highway_major_inner"], { "line-color": "#332f27" }],
    [["highway_major_subtle"], { "line-color": "#2e2b23" }],
    // `aeroway-runway` is a wide line in this style, not a fill -- see the type guard below.
    [["aeroway-runway"], { "line-color": "#1b1813" }],
    [["highway_minor", "highway_motorway_subtle", "aeroway-taxiway"], { "line-color": "#2b2820" }],
    [["highway_path"], { "line-color": "#2a2721" }],
    [
      ["highway_motorway_casing", "highway_major_casing", "aeroway-runway-casing"],
      // Kept translucent, as shipped: casings overlap at junctions and an opaque one builds up
      // into a bright blob exactly where the map is busiest.
      { "line-color": "rgba(86,80,66,0.8)" },
    ],
    [["road_pier"], { "line-color": GROUND_COLOR.dark }],

    [["railway", "railway_minor", "railway_transit"], { "line-color": "#35312a" }],
    // The dashline is drawn *over* the rail line in the ground colour -- that is what makes the
    // sleepers. It has to follow the ground or the dashes stay black.
    [
      ["railway_dashline", "railway_minor_dashline", "railway_transit_dashline"],
      { "line-color": GROUND_COLOR.dark },
    ],
    [["waterway"], { "line-color": "#2a2824" }],
    [["boundary_state"], { "line-color": "#3a352c" }],
    [["boundary_country_z0-4", "boundary_country_z5-"], { "line-color": "#3e3930" }],

    // Labels. The halo is a knockout in the ground colour, so a black one left over a lifted
    // ground rings every place name in soot. The text itself goes up with it -- 3.7:1 against the
    // new ground, a shade better than the 3.4:1 it had against the old one.
    [
      [
        "place_other",
        "place_suburb",
        "place_village",
        "place_town",
        "place_city",
        "place_city_large",
        "place_state",
        "place_country_other",
        "place_country_minor",
        "place_country_major",
      ],
      { "text-color": "#7a7468", "text-halo-color": "rgba(31,28,22,0.75)" },
    ],
    [["highway_name_other"], { "text-color": "#6b665c", "text-halo-color": GROUND_COLOR.dark }],
    [["highway_name_motorway"], { "text-color": "#7a7468" }],
  ],
};

/**
 * Which layer type each property belongs to. A fill's colour is `fill-color` and a line's is
 * `line-color`, and `setPaintProperty` **throws** when handed a property the layer does not have.
 *
 * That is the whole reason this map exists. These handlers run inside `style.load`, before the
 * route layer is added and before `ready` flips, so one wrong pair does not mis-tint one plane --
 * it throws out of the handler and leaves the map with no routes, no markers and no fit, which is
 * how this was found: `aeroway-runway` is a *line* in `dark`, and filing it as a fill killed the
 * entire canvas. A basemap this app does not own is exactly where that must not be possible, so a
 * mismatch is skipped rather than thrown on.
 */
const PROPERTY_LAYER_TYPE: Record<PaintProperty, string> = {
  "background-color": "background",
  "fill-color": "fill",
  "line-color": "line",
  "text-color": "symbol",
  "text-halo-color": "symbol",
};

/**
 * Repaint a loaded style into the app's palette. Safe to call on any style, including one
 * `setStyle` has just swapped in.
 */
export function applyMapPalette(map: MapLibreMap, scheme: ColorScheme): void {
  for (const [ids, paint] of PATCHES[scheme]) {
    for (const id of ids) {
      const layer = map.getLayer(id);
      if (!layer) continue;
      // `Object.entries` widens the key back to `string`; the cast restores what `Group` already
      // guarantees, which is what `setPaintProperty` wants to be told.
      for (const [property, value] of Object.entries(paint) as [PaintProperty, string][]) {
        if (layer.type !== PROPERTY_LAYER_TYPE[property]) continue;
        map.setPaintProperty(id, property, value);
      }
    }
  }
}
