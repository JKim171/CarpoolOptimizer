"use client";

import { useMutation } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { AddressField } from "@/components/AddressField";
import { DestinationMap, type Point } from "@/components/DestinationMap";
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
    <form onSubmit={submit} className="flex flex-col gap-4">
      <label className="block text-sm font-medium">
        Event name
        <input
          className="mt-1 w-full rounded-md border border-black/15 bg-transparent px-3 py-2 text-sm dark:border-white/20"
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="Tuesday practice"
          required
          maxLength={200}
        />
      </label>

      <AddressField
        label="Destination"
        placeholder="500 E Liberty St, Ann Arbor, MI"
        value={address}
        onChange={setAddress}
        onPick={pick}
      />

      <DestinationMap point={point} onMove={setPoint} />

      <div className="grid gap-4 sm:grid-cols-2">
        <label className="block text-sm font-medium">
          Everyone arrives by
          <input
            type="datetime-local"
            className="mt-1 w-full rounded-md border border-black/15 bg-transparent px-3 py-2 text-sm dark:border-white/20"
            value={arrival}
            onChange={(event) => setArrival(event.target.value)}
            required
          />
        </label>
        <label className="block text-sm font-medium">
          Event ends
          <input
            type="datetime-local"
            className="mt-1 w-full rounded-md border border-black/15 bg-transparent px-3 py-2 text-sm dark:border-white/20"
            value={ends}
            onChange={(event) => setEnds(event.target.value)}
            required
          />
        </label>
      </div>

      <label className="block text-sm font-medium">
        Time zone
        <select
          className="mt-1 w-full rounded-md border border-black/15 bg-transparent px-3 py-2 text-sm dark:border-white/20"
          value={timeZone}
          onChange={(event) => setTimeZone(event.target.value)}
        >
          {knownTimeZones().map((zone) => (
            <option key={zone} value={zone}>
              {zone}
            </option>
          ))}
        </select>
        <span className="mt-1 block text-xs font-normal opacity-60">
          Times above are read as the clock in this zone, so the event survives a daylight-saving
          change.
        </span>
      </label>

      {problem && (
        <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-800 dark:bg-red-950 dark:text-red-200">
          {problem}
        </p>
      )}

      <button
        type="submit"
        disabled={create.isPending}
        className="rounded-md bg-blue-700 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
      >
        {create.isPending ? "Creating…" : "Create event"}
      </button>
    </form>
  );
}
