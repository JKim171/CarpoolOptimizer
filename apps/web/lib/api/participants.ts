/**
 * Roster calls.
 *
 * The API has no bulk-add endpoint, so a pasted roster is N sequential POSTs. Sequential rather
 * than parallel on purpose: the participant cap is enforced by bumping the event's version row
 * first, which takes that row's lock, so concurrent adds would serialize on the server anyway --
 * and firing forty at once turns one rejected row into forty ambiguous failures.
 */

import { api, organizerAuth, unwrap } from "./client";
import type { components } from "./schema";

export type Participant = components["schemas"]["ParticipantOrganizerRead"];
export type ParticipantCreate = components["schemas"]["ParticipantCreate"];
export type ParticipantPatch = components["schemas"]["ParticipantPatch"];
export type Roster = components["schemas"]["RosterRead"];

export async function fetchRoster(publicId: string): Promise<Roster> {
  return unwrap(
    await api.GET("/v1/events/{public_id}/participants", {
      params: { path: { public_id: publicId }, header: undefined },
      headers: organizerAuth(publicId),
    }),
  );
}

export async function addParticipant(publicId: string, body: ParticipantCreate) {
  return unwrap(
    await api.POST("/v1/events/{public_id}/participants", {
      params: { path: { public_id: publicId }, header: undefined },
      headers: organizerAuth(publicId),
      body,
    }),
  );
}

export async function patchParticipant(
  publicId: string,
  participantId: string,
  body: ParticipantPatch,
) {
  return unwrap(
    await api.PATCH("/v1/events/{public_id}/participants/{participant_id}", {
      params: {
        path: { public_id: publicId, participant_id: participantId },
        header: undefined,
      },
      headers: organizerAuth(publicId),
      body,
    }),
  );
}

/**
 * Remove someone from the roster.
 *
 * A soft cancel server-side: the row stays with `status = 'cancelled'` so a past solution still
 * resolves the people it assigned. It is idempotent, and it clears any pin pointing at the
 * cancelled person.
 */
export async function cancelParticipant(publicId: string, participantId: string) {
  return unwrap(
    await api.DELETE("/v1/events/{public_id}/participants/{participant_id}", {
      params: {
        path: { public_id: publicId, participant_id: participantId },
        header: undefined,
      },
      headers: organizerAuth(publicId),
    }),
  );
}

export const rosterKeys = {
  all: (publicId: string) => ["roster", publicId] as const,
};

/**
 * The roster, in the order people were added.
 *
 * No filtering by status: `GET /participants` already omits cancelled participants, because they
 * are not on the roster, do not count towards the cap and are not given to the solver. Filtering
 * again here would be dead code implying the opposite -- cancelled rows are reachable only by
 * fetching a participant directly, which a past solution needs and this screen does not.
 */
export function rosterPeople(roster: Roster | undefined): Participant[] {
  return roster?.participants ?? [];
}

/**
 * A participant whose pickup has coordinates.
 *
 * Coordinates are nullable on read by design: from Week 4 a provider-geocoded participant holds
 * none of their own and the solve-time cache supplies them (`PickupRead`). Everything today writes
 * them, but the map must not assume that -- plotting a null reads as a pin at the equator, or as
 * nothing at all, with no indication which.
 */
export type LocatedParticipant = Participant & {
  pickup: Participant["pickup"] & { lat: number; lng: number };
};

export function isLocated(p: Participant): p is LocatedParticipant {
  return typeof p.pickup.lat === "number" && typeof p.pickup.lng === "number";
}
