/**
 * Solutions -- the answer a job produced.
 *
 * A fresh solution is deliberately *not* activated by the API: activation is an organizer's act,
 * and a stale solution can still be activated on purpose (an organizer may prefer a known
 * arrangement to re-solving an hour before the event). So this exposes the read and the activate
 * separately rather than folding them together.
 */

import { api, organizerAuth, unwrap } from "./client";
import type { components } from "./schema";

export type Solution = components["schemas"]["SolutionRead"];
export type Route = components["schemas"]["RouteRead"];
export type Leg = components["schemas"]["LegRead"];
export type Stop = components["schemas"]["StopRead"];
export type Unassigned = components["schemas"]["UnassignedRead"];

/**
 * Which leg is on screen.
 *
 * Note the naming asymmetry, which is easy to get wrong: `RouteRead` calls the fields `outbound`
 * and `inbound`, while the `RouteLeg` enum stored on a leg spells the second one `"return"`.
 */
export type LegChoice = "outbound" | "inbound";

export function legOf(route: Route, choice: LegChoice): Leg {
  return choice === "outbound" ? route.outbound : route.inbound;
}

/**
 * The number a person reads beside a stop.
 *
 * `seq` is 0-based -- it is a list index in the adapter -- and "stop 0" is not something anyone
 * says. Converted here, once, so the list and the numbered map markers cannot disagree about it.
 */
export function stopNumber(stop: Stop): number {
  return stop.seq + 1;
}

export async function fetchSolution(publicId: string, solutionId: string): Promise<Solution> {
  return unwrap(
    await api.GET("/v1/events/{public_id}/solutions/{solution_id}", {
      params: { path: { public_id: publicId, solution_id: solutionId }, header: undefined },
      headers: organizerAuth(publicId),
    }),
  );
}

export async function activateSolution(publicId: string, solutionId: string): Promise<Solution> {
  return unwrap(
    await api.POST("/v1/events/{public_id}/solutions/{solution_id}/activate", {
      params: { path: { public_id: publicId, solution_id: solutionId }, header: undefined },
      headers: organizerAuth(publicId),
    }),
  );
}

export const solutionKeys = {
  detail: (publicId: string, solutionId: string) => ["solution", publicId, solutionId] as const,
};

/**
 * Why somebody was left out, in words an organizer can act on.
 *
 * The domain diagnoses by relaxation and reports the *most actionable* binding constraint, so these
 * strings should read as "here is what to change", not as a classification.
 */
const UNASSIGNED_REASON: Record<string, string> = {
  no_capacity: "No car had a free seat.",
  detour_exceeded: "Picking them up would take a driver too far off their route.",
  time_window: "No car could reach them and still arrive on time.",
  no_drivers: "Nobody on this roster is driving.",
};

export function describeUnassigned(reason: string): string {
  return UNASSIGNED_REASON[reason] ?? reason;
}

/** Integer seconds to something a person reads at a glance. Durations are seconds throughout. */
export function formatDuration(seconds: number): string {
  const total = Math.round(seconds / 60);
  const hours = Math.floor(total / 60);
  const minutes = total % 60;
  if (hours === 0) return `${minutes} min`;
  return minutes === 0 ? `${hours} h` : `${hours} h ${minutes} min`;
}

/** Metres to the nearest tenth of a mile. The audience is a US campus club (docs/design.md 2). */
export function formatDistance(metres: number): string {
  return `${(metres / 1609.344).toFixed(1)} mi`;
}
