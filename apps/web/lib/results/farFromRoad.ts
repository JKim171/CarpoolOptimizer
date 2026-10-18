/**
 * The note for pickups the routing service had to move a long way to reach a road.
 *
 * A snap of hundreds of metres usually means the address geocoded to the wrong place
 * (docs/design.md 7.2). The plan still uses the point, so the note asks for a look rather than
 * calling the address wrong.
 */

import type { FarFromRoad } from "@/lib/api/solutions";

import { formatDistance } from "./distance";

/** One sentence, naming people in the order the API sends them: furthest first. */
export function describeFarFromRoad(far: readonly FarFromRoad[]): string {
  if (far.length === 1) {
    const [only] = far;
    return `${only.display_name}'s pin is ${formatDistance(only.snapped_m)} from the nearest road, so their pickup time may be off. Worth checking their address.`;
  }
  const names = far.map((f) => f.display_name);
  const listed = `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
  return `${listed} have pins well away from the nearest road, so their pickup times may be off. Worth checking their addresses.`;
}
