import { describe, expect, it } from "vitest";

import { describeFarFromRoad } from "./farFromRoad";

const far = (display_name: string, snapped_m: number) => ({
  participant_id: `${display_name}-id`,
  display_name,
  snapped_m,
});

describe("describeFarFromRoad", () => {
  it("names one person and says how far", () => {
    expect(describeFarFromRoad([far("Sam", 480)])).toBe(
      "Sam's pin is 0.3 mi from the nearest road, so their pickup time may be off. Worth checking their address.",
    );
  });

  it("lists several in the order sent", () => {
    expect(describeFarFromRoad([far("Sam", 900), far("Ada", 400), far("Bo", 300)])).toMatch(
      /^Sam, Ada and Bo have pins well away from the nearest road/,
    );
  });
});
