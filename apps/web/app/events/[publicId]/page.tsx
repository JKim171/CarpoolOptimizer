"use client";

/**
 * The organizer's view of one event: the roster, the map that verifies it, and the answer.
 *
 * Everything in one screen rather than a screen each: entering a roster, checking the pins and
 * reading the result are one task done in one sitting, and the loop between them is tight -- an
 * absurd pin is usually spotted *because* the route it produces looks wrong.
 *
 * **The map is the canvas and the panels are the rail** (`components/shell/AppShell.tsx`). This page
 * therefore owns the state the two halves share: which leg, which car is highlighted, and which of
 * the two maps the canvas is showing. The solve itself lives in `useSolution`, which is the top half
 * of what used to be `ResultsPanel`, lifted out when the map stopped being its child.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { use, useState } from "react";

import { ResultsPanel } from "@/components/results/ResultsPanel";
import { RouteMap } from "@/components/results/RouteMap";
import { useSolution } from "@/components/results/useSolution";
import { PickupMap } from "@/components/roster/PickupMap";
import { AddPeople, type AddMode } from "@/components/roster/AddPeople";
import type { DraftPickup } from "@/components/roster/AddParticipantForm";
import { RosterList } from "@/components/roster/RosterList";
import { AppShell, RailSection } from "@/components/shell/AppShell";
import { ThemeToggle } from "@/components/shell/ThemeToggle";
import { Badge, Button, Detail, Notice, Problem } from "@/components/ui/controls";
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

type MapMode = "roster" | "routes";

export default function EventPage({ params }: PageProps<"/events/[publicId]">) {
  const { publicId } = use(params);
  const queryClient = useQueryClient();
  const [highlightedId, setHighlightedId] = useState<string | null>(null);
  /** What the organizer last asked the canvas to show; null means "whatever fits". */
  const [chosenMode, setChosenMode] = useState<MapMode | null>(null);
  const [seenSolutionId, setSeenSolutionId] = useState<string | null>(null);
  /**
   * Which way of adding people is open, and the pickup the single-person form is holding.
   *
   * Both halves of the screen read the pickup -- the form submits it, the canvas draws it and is
   * where it gets placed -- so it belongs to the screen rather than to either one. Same split as
   * the destination on the home screen.
   */
  const [addMode, setAddMode] = useState<AddMode>("paste");
  const [draftPickup, setDraftPickup] = useState<DraftPickup | null>(null);

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
  /**
   * Forget a highlight whose row has gone.
   *
   * Removing someone while hovering their row is the ordinary way to delete them -- the Remove
   * button only appears on hover -- and no `mouseleave` ever fires for a row that stopped
   * existing under the cursor. `highlightedId` would then name a participant who is no longer on
   * the roster, and `PickupMap` reads a set highlight as "the organizer is inspecting something"
   * and suppresses refitting while it lasts. The map therefore stayed framed as it was *before*
   * the delete -- which, when the row deleted was the geocoder's absurd outlier, means it stayed
   * zoomed out around a pin that is no longer there, until some unrelated hover cleared it.
   *
   * Adjusted during render rather than in an effect, like `chosenMode` below: an effect would
   * commit one frame with the stale id and refit a beat later.
   */
  if (highlightedId !== null && roster.isSuccess && !people.some((p) => p.id === highlightedId)) {
    setHighlightedId(null);
  }
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

  const solve = useSolution({
    publicId,
    venue: destination,
    people,
    onRosterChanged: refreshRoster,
  });

  /**
   * An answer takes the canvas when it arrives.
   *
   * That is the point of having asked for one, and leaving the pickup map up would hide the thing
   * the organizer just pressed a button to see. But a deliberate switch back to the pickups has to
   * stick, so the choice is held as "what the organizer last asked for", defaulting to whichever
   * map makes sense, and cleared when a *different* solution shows up -- which includes a
   * re-optimize, since that mints a new id.
   *
   * Adjusting state during render rather than in an effect: it is the pattern React documents for
   * exactly this (a value derived from a prop that must still be overridable), and an effect here
   * would be a second render pass that briefly shows the wrong map.
   */
  const hasSolution = solve.solution !== undefined;
  const solutionId = solve.solution?.id ?? null;
  if (solutionId !== seenSolutionId) {
    setSeenSolutionId(solutionId);
    setChosenMode(null);
  }
  const mode: MapMode = chosenMode ?? (solutionId ? "routes" : "roster");

  const canvasModes = (
    <div
      role="group"
      aria-label="What the map shows"
      className="inline-flex overflow-hidden rounded-[2px] border border-line bg-surface/90 shadow-sm"
    >
      {(["roster", "routes"] as const).map((choice) => (
        <button
          key={choice}
          type="button"
          onClick={() => setChosenMode(choice)}
          aria-pressed={mode === choice}
          disabled={choice === "routes" && !hasSolution}
          className={`px-3 py-1.5 text-sm transition-colors disabled:opacity-40 ${
            mode === choice ? "bg-accent text-accent-ink" : "text-ink hover:bg-surface-sunken"
          }`}
        >
          {choice === "roster" ? "Pickups" : "Routes"}
        </button>
      ))}
    </div>
  );

  const canvas =
    mode === "routes" && hasSolution ? (
      <RouteMap
        routes={solve.mapped}
        venue={destination}
        leg={solve.leg}
        highlightedRouteId={solve.highlightedRouteId}
        overlay={canvasModes}
      />
    ) : (
      <PickupMap
        participants={located}
        destination={destination}
        highlightedId={highlightedId}
        onHighlight={setHighlightedId}
        overlay={canvasModes}
        onMove={(id, point) => {
          const person = people.find((p) => p.id === id);
          if (!person) return;
          // The address stays as it was: dragging corrects where the person is, not what their
          // address says. The pair still moves together, which is what matters.
          patch.mutate({
            id,
            body: { pickup: { address: person.pickup.address, ...point } },
          });
        }}
        draft={draftPickup}
        onDraft={(point) => setDraftPickup({ ...point, byHand: true })}
        // Only while that form is the open tab: on the paste tab a click on the map is someone
        // reading it, and dropping a stray pin there would be an answer to a question nobody asked.
        placing={addMode === "one"}
      />
    );

  const rail = (
    <>
      <div className="flex flex-col gap-3 px-5 pb-5 pt-6">
        {/* The back link and the theme control share the top row: both are chrome rather than
            part of this event, and the event's own title comes below them. */}
        <div className="flex items-center justify-between gap-3">
          <Link href="/" className="text-sm text-accent underline underline-offset-2">
            ← All events
          </Link>
          <ThemeToggle />
        </div>

        {event.isPending && <p className="text-sm text-ink-muted">Loading…</p>}

        {event.isError && (
          // The API answers an unknown event, a revoked token and another event's token all with
          // 401, deliberately, so that the status cannot be used to discover which handles are real
          // (docs/design.md 6.1). The UI cannot tell them apart either, and must not pretend to.
          <Problem>
            {event.error instanceof ApiError
              ? event.error.message
              : "Could not load this event. Check your connection and try again."}
          </Problem>
        )}

        {event.isSuccess && (
          <>
            <h1 className="font-display text-2xl text-ink">{event.data.name}</h1>
            <div className="flex flex-wrap items-baseline gap-2">
              <Badge mono>{publicId}</Badge>
              <Badge>{event.data.status}</Badge>
              <Badge>
                {people.length} of {MAX_PARTICIPANTS} on the roster
              </Badge>
            </div>
            {/* Stacked rather than three across: the rail has one column, not three. */}
            <dl className="flex flex-col gap-3 border-t border-line pt-4">
              <Detail label="Destination">{event.data.destination.address}</Detail>
              <Detail label="Everyone arrives by">
                {formatInZone(new Date(event.data.arrival_at), event.data.timezone)}
              </Detail>
              <Detail label="Event ends">
                {formatInZone(new Date(event.data.ends_at), event.data.timezone)}
              </Detail>
            </dl>
          </>
        )}
      </div>

      {event.isSuccess && (
        <>
          {/*
            The answer comes first in the rail, above the roster that produced it. In the document
            version it came last, on the reasoning that inputs precede outputs -- but that put it
            below a fifty-row roster and two forms, and the canvas beside it is already showing the
            routes. A panel that explains what is on screen belongs where the eye lands.
          */}
          <RailSection
            title="Who drives who"
            meta={solve.jobDescription}
            actions={
              <Button onClick={solve.start} disabled={solve.busy || people.length === 0}>
                {solve.solution ? "Re-optimize" : "Work out the carpools"}
              </Button>
            }
          >
            <ResultsPanel solve={solve} timeZone={event.data.timezone} rosterSize={people.length} />
          </RailSection>

          <RailSection title="Roster" meta={roster.isFetching ? "Refreshing…" : undefined}>
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

            {roster.isSuccess && (
              <RosterList
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
          </RailSection>

          <RailSection title="Add people">
            {seatsLeft === 0 ? (
              <Problem>
                This roster is full at {MAX_PARTICIPANTS} people. Remove someone before adding
                another.
              </Problem>
            ) : (
              <AddPeople
                publicId={publicId}
                seatsLeft={seatsLeft}
                onChanged={refreshRoster}
                mode={addMode}
                onMode={setAddMode}
                pickup={draftPickup}
                onPickup={setDraftPickup}
              />
            )}
          </RailSection>
        </>
      )}
    </>
  );

  return <AppShell rail={rail} canvas={canvas} />;
}
