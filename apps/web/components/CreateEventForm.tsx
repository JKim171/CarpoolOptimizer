"use client";

import { useMutation } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { AddressField } from "@/components/AddressField";
import { DestinationMap, type Point } from "@/components/DestinationMap";
import { Button, Field, Problem, Select, TextInput } from "@/components/ui/controls";
import { ApiError } from "@/lib/api/client";
import { createEvent } from "@/lib/api/events";
import type { Place } from "@/lib/api/geocode";
import { knownTimeZones, localTimeZone, wallClockToInstant } from "@/lib/time";

export function CreateEventForm() {
  const router = useRouter();

  const [name, setName] = useState("");
  const [address, setAddress] = useState("");
  const [point, setPoint] = useState<Point | null>(null);
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
      setProblem("Choose a destination, or place the pin on the map.");
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
    setAddress(place.address);
    setPoint({ lat: place.lat, lng: place.lng });
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-5">
      <Field label="Event name">
        <TextInput
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="Tuesday practice"
          required
          maxLength={200}
        />
      </Field>

      <AddressField
        label="Destination"
        placeholder="500 E Liberty St, Ann Arbor, MI"
        value={address}
        onChange={setAddress}
        onPick={pick}
      />

      <DestinationMap point={point} onMove={setPoint} />

      <div className="grid gap-5 sm:grid-cols-2">
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
      </div>

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

      <Button type="submit" disabled={create.isPending}>
        {create.isPending ? "Creating…" : "Create event"}
      </Button>
    </form>
  );
}
