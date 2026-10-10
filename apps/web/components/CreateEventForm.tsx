"use client";

/**
 * The new-event form, as the rail half of a map-and-panel screen.
 *
 * **The destination map used to be inside this form.** It is now the shell's canvas, so the point
 * being picked is state this component no longer owns -- it is lifted to the home screen, which
 * renders both halves. That is the same split the event screen makes for the same reason: the map
 * is the canvas, and anything both halves read belongs to the screen rather than to either one.
 *
 * Nothing here caps its own width any more. The rail is the measure.
 */

import { useMutation } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { AddressField } from "@/components/AddressField";
import type { Point } from "@/components/DestinationMap";
import { Button, Field, Problem, Select, TextInput } from "@/components/ui/controls";
import { ApiError } from "@/lib/api/client";
import { createEvent } from "@/lib/api/events";
import type { Place } from "@/lib/api/geocode";
import { knownTimeZones, localTimeZone, wallClockToInstant } from "@/lib/time";

export function CreateEventForm({
  address,
  onAddress,
  point,
  onPoint,
}: {
  address: string;
  onAddress: (address: string) => void;
  point: Point | null;
  onPoint: (point: Point | null) => void;
}) {
  const router = useRouter();

  const [name, setName] = useState("");
  const [timeZone, setTimeZone] = useState(localTimeZone);
  const [arrival, setArrival] = useState("");
  const [ends, setEnds] = useState("");
  const [problem, setProblem] = useState<string | null>(null);

  const create = useMutation({
    mutationFn: createEvent,
    onSuccess: (created) => router.push(`/events/${created.event.public_id}`),
    onError: (error) =>
      setProblem(error instanceof ApiError ? error.message : "Could not create the event."),
  });

  function submit(formEvent: React.FormEvent) {
    formEvent.preventDefault();
    setProblem(null);

    // Validated here as well as server-side so the coordinator gets the message next to the field
    // rather than as a 422 after a round trip.
    if (!point) {
      setProblem("Choose a destination from the suggestions, or click the map to place the pin.");
      return;
    }
    if (!address.trim()) {
      // Reachable only since a click can place the pin without the field being touched. The
      // coordinate tells the solver where to go; the text is what the event page shows an
      // organizer, and the API requires it.
      setProblem("Add an address or a name for the destination, so the event says where it is.");
      return;
    }
    const arrivalAt = wallClockToInstant(arrival, timeZone);
    const endsAt = wallClockToInstant(ends, timeZone);
    if (!arrivalAt || !endsAt) {
      setProblem("Enter both an arrival time and an end time.");
      return;
    }
    if (endsAt <= arrivalAt) {
      // Mirrors `ck_events_ends_after_arrival` and ProblemInstance's own rule.
      setProblem("The event must end after everyone is due to arrive.");
      return;
    }

    create.mutate({
      name: name.trim(),
      destination: { address: address.trim(), lat: point.lat, lng: point.lng },
      arrival_at: arrivalAt.toISOString(),
      ends_at: endsAt.toISOString(),
      timezone: timeZone,
    });
  }

  function pick(place: Place) {
    onAddress(place.address);
    onPoint({ lat: place.lat, lng: place.lng });
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-4">
      <Field label="Event name">
        <TextInput
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="Tuesday practice"
          required
          maxLength={200}
        />
      </Field>

      {/*
        **The example is one the geocoder can actually find.** This read `500 E Liberty St, Ann
        Arbor, MI`, which the provider's autocomplete returns nothing for -- so the first thing a
        new organizer typed, copied from the app's own prompt, answered "No matches". A named venue
        is the better prompt anyway: it is what a destination usually is, and it is the case the
        drag-to-adjust below exists for (a school geocodes to its building, not to its car park).
      */}
      <AddressField
        label="Destination"
        placeholder="Pioneer High School, Ann Arbor"
        resolved={point !== null}
        value={address}
        onChange={onAddress}
        onPick={pick}
      />

      <Field label="Everyone arrives by">
        <TextInput
          type="datetime-local"
          value={arrival}
          onChange={(event) => setArrival(event.target.value)}
          required
        />
      </Field>
      <Field label="Event ends">
        <TextInput
          type="datetime-local"
          value={ends}
          onChange={(event) => setEnds(event.target.value)}
          required
        />
      </Field>

      <Field
        label="Time zone"
        hint="Times above are read as the clock in this zone, so the event survives a daylight-saving change."
      >
        <Select value={timeZone} onChange={(event) => setTimeZone(event.target.value)}>
          {knownTimeZones().map((zone) => (
            <option key={zone} value={zone}>
              {zone}
            </option>
          ))}
        </Select>
      </Field>

      {problem && <Problem>{problem}</Problem>}

      {/* The wrapper is load-bearing: the form is a column flexbox, so a bare child stretches to
          the full measure, which a button does not want. Same shape as `AddParticipantForm`. */}
      <div>
        <Button type="submit" disabled={create.isPending}>
          {create.isPending ? "Creating…" : "Create event"}
        </Button>
      </div>
    </form>
  );
}
