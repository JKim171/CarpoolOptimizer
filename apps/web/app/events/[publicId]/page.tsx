"use client";

/**
 * The organizer's view of one event: the roster, the map that verifies it, and the answer.
 *
 * All on one page rather than a screen each: entering a roster, checking the pins and reading the
 * result are one task done in one sitting, and the loop between them is tight -- an absurd pin is
 * usually spotted *because* the route it produces looks wrong.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { use, useState } from "react";

import { ResultsPanel } from "@/components/results/ResultsPanel";
import { PickupMap } from "@/components/roster/PickupMap";
import { AddParticipantForm } from "@/components/roster/AddParticipantForm";
import { PasteRoster } from "@/components/roster/PasteRoster";
import { RosterTable } from "@/components/roster/RosterTable";
import { Badge, Detail, Notice, Page, Panel, Problem, Section } from "@/components/ui/controls";
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
        <Link href="/" className="text-sm text-accent underline underline-offset-2">
          ← All events
        </Link>
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
          <header className="flex flex-col gap-5">
            {/*
              The handle, the status and the roster count are facts *about* the event rather than
              details of it, and as `Detail` cells they carried the same weight as the destination
              and the arrival time -- "Status: open" is not a third of what this header has to say.
              As chips beside the title they are available without competing.
            */}
            <div className="flex flex-wrap items-baseline gap-x-3 gap-y-2">
              <h1 className="font-display text-4xl text-ink sm:text-5xl">{event.data.name}</h1>
              <Badge mono>{publicId}</Badge>
              <Badge>{event.data.status}</Badge>
              <Badge>
                {people.length} of {MAX_PARTICIPANTS} on the roster
              </Badge>
            </div>
            {/*
              Three cells, not six, and divided by rules rather than boxed. The time zone was its
              own cell and is redundant: `formatInZone` already prints the abbreviation on both
              times, which is the form anybody reads it in.
            */}
            {/*
              `border-t` only. A bottom rule here and the rule that opens the next section are
              forty pixels apart with nothing between them, which reads as an empty band rather
              than as two divisions.
            */}
            <dl className="grid gap-5 border-t border-line pt-5 sm:grid-cols-3">
              <Detail label="Destination">{event.data.destination.address}</Detail>
              <Detail label="Everyone arrives by">
                {formatInZone(new Date(event.data.arrival_at), event.data.timezone)}
              </Detail>
              <Detail label="Event ends">
                {formatInZone(new Date(event.data.ends_at), event.data.timezone)}
              </Detail>
            </dl>
          </header>

          <Section title="Roster" meta={roster.isFetching ? "Refreshing…" : undefined}>
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
              <Notice>
                {unlocated} {unlocated === 1 ? "person has" : "people have"} no coordinates yet and{" "}
                {unlocated === 1 ? "is" : "are"} not on the map. Edit the row to set an address.
              </Notice>
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
          </Section>

          <Section title="Add people">
            {seatsLeft === 0 ? (
              <Problem>
                This roster is full at {MAX_PARTICIPANTS} people. Remove someone before adding
                another.
              </Problem>
            ) : (
              <PasteRoster publicId={publicId} seatsLeft={seatsLeft} onImported={refreshRoster} />
            )}

            <Panel title="Or add one person">
              <AddParticipantForm
                publicId={publicId}
                disabled={seatsLeft === 0}
                onAdded={refreshRoster}
              />
            </Panel>
          </Section>

          {/*
            Last, after the roster and the ways of adding to it: inputs then output, which is both
            reading order and the order the work happens in. It also keeps "add one person" within
            reach of the table it appends to, rather than below a full set of results.
          */}
          <ResultsPanel
            publicId={publicId}
            venue={destination}
            timeZone={event.data.timezone}
            people={people}
            onRosterChanged={refreshRoster}
          />
        </>
      )}
    </Page>
  );
}
