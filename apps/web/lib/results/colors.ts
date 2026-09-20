/**
 * One colour per car, shared by the map and the list beside it.
 *
 * The colour is the only thing tying "Maya's car" in the list to a line on the map, so it has to be
 * assigned in one place. Read off the route's position in the solution, which is stable for as long
 * as a solution exists -- re-solving may recolour, and that is correct: it is a different answer.
 *
 * Chosen to stay legible *on a light basemap* rather than against the page, which is the harder
 * constraint: these sit on top of streets and parkland. Deliberately excludes the dark red the
 * destination marker uses, so the venue never reads as somebody's car.
 */
const ROUTE_COLORS = [
  "#1d4ed8", // blue
  "#047857", // green
  "#b45309", // amber
  "#7c3aed", // violet
  "#0369a1", // sky
  "#a21caf", // fuchsia
  "#4d7c0f", // olive
  "#c2410c", // orange
] as const;

/** The venue. A shape of its own on the map too, so this is not the only thing distinguishing it. */
export const DESTINATION_COLOR = "#991b1b";

/**
 * Cars beyond the palette wrap around and share a colour. With a 50-person cap and a realistic
 * seat count that needs ~9 cars before it happens, and the list stays unambiguous when it does.
 */
export function routeColor(index: number): string {
  return ROUTE_COLORS[index % ROUTE_COLORS.length];
}
