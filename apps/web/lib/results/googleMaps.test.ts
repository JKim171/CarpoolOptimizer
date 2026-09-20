import { describe, expect, it } from "vitest";

import { directionsUrl, legWaypoints, TooManyStops } from "./googleMaps";

const HOME = { lat: 42.29799, lng: -83.79543 };
const VENUE = { lat: 42.24626, lng: -83.78698 };
const A = { lat: 42.24136, lng: -83.68887 };
const B = { lat: 42.31776, lng: -83.7448 };

function paramsOf(url: string): URLSearchParams {
  return new URL(url).searchParams;
}

describe("directionsUrl", () => {
  it("puts origin, destination and ordered waypoints into the api=1 URL", () => {
    const params = paramsOf(directionsUrl({ origin: HOME, destination: VENUE, stops: [A, B] }));

    expect(params.get("api")).toBe("1");
    expect(params.get("travelmode")).toBe("driving");
    expect(params.get("origin")).toBe("42.297990,-83.795430");
    expect(params.get("destination")).toBe("42.246260,-83.786980");
    expect(params.get("waypoints")).toBe("42.241360,-83.688870|42.317760,-83.744800");
  });

  it("preserves stop order, because the order is the whole answer", () => {
    // A solver that returns B before A has produced a different route. Two links that differ only
    // in waypoint order must not be equal -- this is the mistake that is invisible on screen.
    const forward = paramsOf(directionsUrl({ origin: HOME, destination: VENUE, stops: [A, B] }));
    const reverse = paramsOf(directionsUrl({ origin: HOME, destination: VENUE, stops: [B, A] }));

    expect(forward.get("waypoints")).not.toBe(reverse.get("waypoints"));
  });

  it("omits waypoints entirely when the driver rides alone", () => {
    const params = paramsOf(directionsUrl({ origin: HOME, destination: VENUE, stops: [] }));

    expect(params.has("waypoints")).toBe(false);
    expect(params.get("origin")).toBe("42.297990,-83.795430");
  });

  it("refuses more stops than the URL format carries, rather than dropping them", () => {
    const tooMany = Array.from({ length: 10 }, (_, i) => ({ lat: 42 + i / 100, lng: -83 }));

    expect(() => directionsUrl({ origin: HOME, destination: VENUE, stops: tooMany })).toThrow(
      TooManyStops,
    );
  });
});

describe("legWaypoints", () => {
  it("runs home to venue on the outbound", () => {
    const plan = legWaypoints({
      leg: "outbound",
      driverHome: HOME,
      venue: VENUE,
      stops: [A, B],
    });

    expect(plan.origin).toEqual(HOME);
    expect(plan.destination).toEqual(VENUE);
    expect(plan.stops).toEqual([A, B]);
  });

  it("runs venue to home on the return", () => {
    const plan = legWaypoints({ leg: "inbound", driverHome: HOME, venue: VENUE, stops: [A, B] });

    expect(plan.origin).toEqual(VENUE);
    expect(plan.destination).toEqual(HOME);
  });

  it("does not reverse the return's stop order", () => {
    // Each leg is sequenced independently against an asymmetric matrix (docs/design.md 8.2), so the
    // return's `seq` is already the order to drive. Reversing it here would silently undo that --
    // and under the haversine provider, where the matrix *is* symmetric, the bug would be invisible
    // until real routing data landed (trap 51).
    const plan = legWaypoints({ leg: "inbound", driverHome: HOME, venue: VENUE, stops: [A, B] });

    expect(plan.stops).toEqual([A, B]);
  });
});
