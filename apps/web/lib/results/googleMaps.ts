/**
 * Turn one leg of one car into a Google Maps directions link.
 *
 * This is the hand-off out of the product: the organizer's job ends at "who drives whom, in what
 * order", and the driver's begins with turn-by-turn navigation somewhere else. Route *geometry* is
 * deliberately never fetched per solve -- the provider's directions quota (2,000/day, 40/min) binds
 * long before the matrix quota does -- so the app does not draw the driving path, and this link is
 * what supplies it, for free, at the moment one person actually needs it.
 *
 * Pure on purpose: a URL builder that reaches for the network or the clock cannot be tested, and
 * this is the piece where an ordering mistake is invisible on screen and wrong in the car.
 */

export type Waypoint = { lat: number; lng: number };

/**
 * Google's documented cap for the `api=1` directions URL. A car seats at most 8 (`MAX_SEATS` in the
 * roster parser), so a legitimate leg cannot exceed it -- this guards against a malformed solution
 * silently producing a link that drops stops, which is the failure mode that would matter.
 */
const MAX_WAYPOINTS = 9;

/** Six decimal places is ~0.1 m. More is noise, and it makes the URLs unreadable. */
function coord(point: Waypoint): string {
  return `${point.lat.toFixed(6)},${point.lng.toFixed(6)}`;
}

export class TooManyStops extends Error {
  constructor(count: number) {
    super(`A directions link takes at most ${MAX_WAYPOINTS} intermediate stops, not ${count}.`);
    this.name = "TooManyStops";
  }
}

/**
 * Build the link.
 *
 * Coordinates rather than address strings, deliberately: the addresses came from a geocoder that
 * may have reformatted them, and re-geocoding a reformatted string inside Google can land somewhere
 * else again. The coordinate is the thing the solver actually routed on, and it is what the
 * organizer verified on the map.
 */
export function directionsUrl({
  origin,
  destination,
  stops,
}: {
  origin: Waypoint;
  destination: Waypoint;
  stops: Waypoint[];
}): string {
  if (stops.length > MAX_WAYPOINTS) throw new TooManyStops(stops.length);

  const params = new URLSearchParams({
    api: "1",
    origin: coord(origin),
    destination: coord(destination),
    travelmode: "driving",
  });
  if (stops.length > 0) {
    // `URLSearchParams` percent-encodes the `|` separator, which Google accepts.
    params.set("waypoints", stops.map(coord).join("|"));
  }
  return `https://www.google.com/maps/dir/?${params.toString()}`;
}

/**
 * The stop sequence for a leg, as a driver drives it.
 *
 * Outbound a driver leaves home, collects riders in `seq` order and ends at the venue. The return
 * is not that route reversed -- each leg is sequenced independently against an asymmetric travel
 * matrix (docs/design.md 8.2) -- so it starts at the venue, drops riders in *its own* `seq` order,
 * and ends at the driver's home.
 */
export function legWaypoints({
  leg,
  driverHome,
  venue,
  stops,
}: {
  leg: "outbound" | "inbound";
  driverHome: Waypoint;
  venue: Waypoint;
  stops: Waypoint[];
}): { origin: Waypoint; destination: Waypoint; stops: Waypoint[] } {
  return leg === "outbound"
    ? { origin: driverHome, destination: venue, stops }
    : { origin: venue, destination: driverHome, stops };
}
