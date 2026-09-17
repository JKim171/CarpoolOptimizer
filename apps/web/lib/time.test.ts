/**
 * Timezone conversion, pinned at the boundaries where it silently breaks.
 *
 * These are not "does the library work" tests. Each one is a case where a plausible hand-rolled
 * implementation returns a time that is wrong by exactly one hour -- which looks like a typo in the
 * roster rather than a bug, and puts a driver at a door at the wrong time.
 */

import { describe, expect, it } from "vitest";

import { instantToWallClock, wallClockToInstant } from "./time";

const DETROIT = "America/Detroit";

describe("wallClockToInstant", () => {
  it("reads a winter time as EST (UTC-5)", () => {
    const instant = wallClockToInstant("2026-01-20T16:00", DETROIT);

    expect(instant?.toISOString()).toBe("2026-01-20T21:00:00.000Z");
  });

  it("reads a summer time as EDT (UTC-4)", () => {
    // Same wall clock, same zone, one hour's difference in the instant. A fixed offset would get
    // one of these two tests wrong, and nothing in the UI would show it.
    const instant = wallClockToInstant("2026-07-20T16:00", DETROIT);

    expect(instant?.toISOString()).toBe("2026-07-20T20:00:00.000Z");
  });

  it("handles the evening before a spring-forward without drifting", () => {
    // DST begins 2026-03-08 in the US. The day either side is where off-by-one-day arithmetic and
    // off-by-one-hour offsets both show up.
    const instant = wallClockToInstant("2026-03-07T22:00", DETROIT);

    expect(instant?.toISOString()).toBe("2026-03-08T03:00:00.000Z");
  });

  it("handles the evening after a spring-forward", () => {
    const instant = wallClockToInstant("2026-03-08T22:00", DETROIT);

    expect(instant?.toISOString()).toBe("2026-03-09T02:00:00.000Z");
  });

  it("respects the zone it is given rather than the machine's", () => {
    // The whole point of storing a zone name: a coordinator in one zone can run an event in
    // another, and this must not quietly use wherever the browser happens to be.
    const detroit = wallClockToInstant("2026-07-20T16:00", DETROIT);
    const los_angeles = wallClockToInstant("2026-07-20T16:00", "America/Los_Angeles");

    expect(detroit?.toISOString()).not.toBe(los_angeles?.toISOString());
    expect(los_angeles?.toISOString()).toBe("2026-07-20T23:00:00.000Z");
  });

  it("returns null for an empty or malformed field", () => {
    // A half-filled form must produce a validation message, not `Invalid Date` serialized into
    // the request body.
    expect(wallClockToInstant("", DETROIT)).toBeNull();
    expect(wallClockToInstant("not a date", DETROIT)).toBeNull();
  });
});

describe("instantToWallClock", () => {
  it("round-trips a summer time", () => {
    const value = "2026-07-20T16:00";

    const instant = wallClockToInstant(value, DETROIT)!;

    expect(instantToWallClock(instant, DETROIT)).toBe(value);
  });

  it("round-trips a winter time", () => {
    const value = "2026-01-20T16:00";

    const instant = wallClockToInstant(value, DETROIT)!;

    expect(instantToWallClock(instant, DETROIT)).toBe(value);
  });

  it("renders an instant in the event's zone, not the machine's", () => {
    const instant = new Date("2026-07-20T20:00:00.000Z");

    expect(instantToWallClock(instant, DETROIT)).toBe("2026-07-20T16:00");
    expect(instantToWallClock(instant, "America/Los_Angeles")).toBe("2026-07-20T13:00");
  });
});
