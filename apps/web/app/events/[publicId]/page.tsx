"use client";

/**
 * The organizer's view of one event: the roster, and the map that verifies it.
 *
 * The results view lands in the next slice. This page is already the one an organizer returns to,
 * so the roster lives here rather than on a screen of its own -- entering a roster and checking the
 * pins are two halves of the same task.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { use, useState } from "react";

import { PickupMap } from "@/components/roster/PickupMap";
import { AddParticipantForm } from "@/components/roster/AddParticipantForm";
import { PasteRoster } from "@/components/roster/PasteRoster";
import { RosterTable } from "@/components/roster/RosterTable";
import { Detail, Page, Panel, Problem } from "@/components/ui/controls";
import { ApiError } from "@/lib/api/client";
import { eventKeys, fetchEvent } from "@/lib/api/events";
import {
  rosterPeople,
  cancelParticipant,
  fetchRoster,
  isLocated,
  patchParticipant,
  rosterKeys,
  type ParticipantPatch,
} from "@/lib/api/participants";
import { formatInZone } from "@/lib/time";

/**
 * Mirrors `MAX_ACTIVE_PARTICIPANTS` in the API, which sizes the roster so a 51x51 matrix fits the
 * provider's 3,500-element limit without tiling. Duplicated here only to warn before a request the
 * server would reject; the API remains the enforcement point.
 */
const MAX_PARTICIPANTS = 50;

export default function EventPage({ params }: PageProps<"/events/[publicId]">) {
  const { publicId } = use(params);
  const queryClient = useQueryClient();
  const [highlightedId, setHighlightedId] = useState<string | null>(null);

  const event = useQuery({
    queryKey: eventKeys.detail(publicId),
    queryFn: () => fetchEvent(publicId),
  });

  const roster = useQuery({
    queryKey: rosterKeys.all(publicId),
    queryFn: () => fetchRoster(publicId),
    // Only once the event has loaded: an invalid token fails both, and one error is enough.
    enabled: event.isSuccess,
  });

  const refreshRoster = () => {
    void queryClient.invalidateQueries({ queryKey: rosterKeys.all(publicId) });
    // The roster version lives on the event, and a stale one would misreport the cap.
    void queryClient.invalidateQueries({ queryKey: eventKeys.detail(publicId) });
  };

  const patch = useMutation({
    mutationFn: ({ id, body }: { id: string; body: ParticipantPatch }) =>
      patchParticipant(publicId, id, body),
    onSuccess: refreshRoster,
  });

  const remove = useMutation({
    mutationFn: (id: string) => cancelParticipant(publicId, id),
    onSuccess: refreshRoster,
  });

  const people = rosterPeople(roster.data);
  // Everything written today carries coordinates, but they are nullable on read by design, so the
  // map plots only those that have them rather than assuming.
  const located = people.filter(isLocated);
  const unlocated = people.length - located.length;
  const seatsLeft = Math.max(MAX_PARTICIPANTS - people.length, 0);
  const destination = event.data
    ? {
        address: event.data.destination.address,
        lat: event.data.destination.lat,
        lng: event.data.destination.lng,
      }
    : null;

  return (
    <Page>
      <div>
        <Link href="/" className="text-sm text-accent hover:underline">
          ← All events
        </Link>
        <p className="mt-2 font-mono text-xs text-ink-muted">{publicId}</p>
      </div>

      {event.isPending && <p className="text-sm text-ink-muted">Loading…</p>}

      {event.isError && (
        // The API answers an unknown event, a revoked token and another event's token all with 401,
        // deliberately, so that the status cannot be used to discover which handles are real
        // (docs/design.md 6.1). The UI cannot tell them apart either, and must not pretend to.
        <Problem>
          {event.error instanceof ApiError
            ? event.error.message
            : "Could not load this event. Check your connection and try again."}
        </Problem>
      )}

      {event.isSuccess && (
        <>
          <h1 className="text-2xl font-semibold text-ink">{event.data.name}</h1>
          <dl className="grid gap-4 sm:grid-cols-2">
            <Detail label="Destination">{event.data.destination.address}</Detail>
            <Detail label="Status">{event.data.status}</Detail>
            <Detail label="Everyone arrives by">
              {formatInZone(new Date(event.data.arrival_at), event.data.timezone)}
            </Detail>
            <Detail label="Event ends">
              {formatInZone(new Date(event.data.ends_at), event.data.timezone)}
            </Detail>
            <Detail label="Time zone">{event.data.timezone}</Detail>
            <Detail label="On the roster">
              {people.length} of {MAX_PARTICIPANTS}
            </Detail>
          </dl>

          <section className="flex flex-col gap-3">
            <div className="flex items-baseline justify-between">
              <h2 className="text-sm font-medium text-ink">Roster</h2>
              {roster.isFetching && <span className="text-xs text-ink-muted">Refreshing…</span>}
            </div>

            {roster.isError && (
              <Problem>
                {roster.error instanceof ApiError
                  ? roster.error.message
                  : "Could not load the roster."}
              </Problem>
            )}

            {(patch.isError || remove.isError) && (
              <Problem>
                {(patch.error ?? remove.error) instanceof ApiError
                  ? (patch.error ?? remove.error)!.message
                  : "That change could not be saved."}
              </Problem>
            )}

            {unlocated > 0 && (
              <p className="text-sm text-warn-ink">
                {unlocated} {unlocated === 1 ? "person has" : "people have"} no coordinates yet and{" "}
                {unlocated === 1 ? "is" : "are"} not on the map. Edit the row to set an address.
              </p>
            )}

            <PickupMap
              participants={located}
              destination={destination}
              highlightedId={highlightedId}
              onHighlight={setHighlightedId}
              onMove={(id, point) => {
                const person = people.find((p) => p.id === id);
                if (!person) return;
                // The address stays as it was: dragging corrects where the person is, not what
                // their address says. The pair still moves together, which is what matters.
                patch.mutate({
                  id,
                  body: { pickup: { address: person.pickup.address, ...point } },
                });
              }}
            />

            {roster.isSuccess && (
              <RosterTable
                participants={people}
                highlightedId={highlightedId}
                onHighlight={setHighlightedId}
                onPatch={async (id, body) => {
                  await patch.mutateAsync({ id, body });
                }}
                onCancel={async (id) => {
                  await remove.mutateAsync(id);
                }}
                busyId={remove.isPending ? remove.variables : null}
              />
            )}
          </section>

          <section className="flex flex-col gap-3">
            <h2 className="text-sm font-medium text-ink">Add people</h2>
            {seatsLeft === 0 ? (
              <Problem>
                This roster is full at {MAX_PARTICIPANTS} people. Remove someone before adding
                another.
              </Problem>
            ) : (
              <PasteRoster publicId={publicId} seatsLeft={seatsLeft} onImported={refreshRoster} />
            )}

            <Panel>
              <h3 className="mb-3 text-sm font-medium text-ink">Or add one person</h3>
              <AddParticipantForm
                publicId={publicId}
                disabled={seatsLeft === 0}
                onAdded={refreshRoster}
              />
            </Panel>
          </section>
        </>
      )}
    </Page>
  );
}
