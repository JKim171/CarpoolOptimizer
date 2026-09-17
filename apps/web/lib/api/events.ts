/**
 * Event calls. Thin wrappers so components never build a path or a header by hand.
 */

import { api, organizerAuth, unwrap } from "./client";
import type { components } from "./schema";
import { writeToken } from "./tokens";

export type Event = components["schemas"]["EventOrganizerRead"];
export type EventCreate = components["schemas"]["EventCreate"];

/**
 * Create an event and keep its organizer token.
 *
 * **The token is shown exactly once** -- only its digest is stored server-side, so a token that is
 * not saved here cannot be recovered, only reissued (docs/design.md 6). Storing it before returning
 * is therefore not a convenience; skipping it loses access to the event that was just created.
 */
export async function createEvent(body: EventCreate) {
  const created = unwrap(await api.POST("/v1/events", { body }));
  writeToken(created.event.public_id, created.organizer_token);
  return created;
}

export async function fetchEvent(publicId: string): Promise<Event> {
  return unwrap(
    await api.GET("/v1/events/{public_id}", {
      params: { path: { public_id: publicId }, header: undefined },
      headers: organizerAuth(publicId),
    }),
  );
}

/** Query key factory, so a mutation can invalidate exactly what it changed. */
export const eventKeys = {
  detail: (publicId: string) => ["event", publicId] as const,
};
