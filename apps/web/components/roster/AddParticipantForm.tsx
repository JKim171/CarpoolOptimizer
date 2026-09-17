"use client";

/**
 * Add one person.
 *
 * The fallback beside the paste path, and the only way in for the rows paste could not resolve: it
 * accepts a pin placed by hand, so a house the geocoder has never heard of is still enterable.
 */

import { useState } from "react";

import { AddressField } from "@/components/AddressField";
import { Button, Field, Problem, Select, TextInput } from "@/components/ui/controls";
import { ApiError } from "@/lib/api/client";
import type { Place } from "@/lib/api/geocode";
import { addParticipant } from "@/lib/api/participants";

export function AddParticipantForm({
  publicId,
  disabled,
  onAdded,
}: {
  publicId: string;
  disabled: boolean;
  onAdded: () => void;
}) {
  const [name, setName] = useState("");
  const [address, setAddress] = useState("");
  const [point, setPoint] = useState<{ lat: number; lng: number } | null>(null);
  const [role, setRole] = useState<"passenger" | "driver">("passenger");
  const [seats, setSeats] = useState("1");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);

    if (!point) {
      setError("Choose an address from the suggestions so the pickup has coordinates.");
      return;
    }

    setBusy(true);
    try {
      await addParticipant(publicId, {
        display_name: name.trim(),
        role,
        // A passenger may not hold seats -- the API answers 422, so send the pair it accepts.
        seats_available: role === "driver" ? Math.max(Number.parseInt(seats, 10) || 1, 1) : 0,
        pickup: { address, lat: point.lat, lng: point.lng },
        // Required by the generated types: every field carrying a server-side default is stated.
        needs_outbound: true,
        needs_return: true,
        priority: 0,
      });
      setName("");
      setAddress("");
      setPoint(null);
      setRole("passenger");
      setSeats("1");
      onAdded();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not add that person.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-3">
      <Field label="Name">
        <TextInput
          value={name}
          required
          maxLength={120}
          onChange={(e) => setName(e.target.value)}
          placeholder="Ana Ruiz"
        />
      </Field>

      <AddressField
        label="Pickup address"
        value={address}
        placeholder="12 Oak St, Ann Arbor"
        onChange={(v) => {
          setAddress(v);
          // Typing after picking invalidates the coordinates: the two must move together, or the
          // row says one thing and the solver routes by another.
          setPoint(null);
        }}
        onPick={(place: Place) => {
          setAddress(place.address);
          setPoint({ lat: place.lat, lng: place.lng });
        }}
      />

      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Role">
          <Select value={role} onChange={(e) => setRole(e.target.value as "passenger" | "driver")}>
            <option value="passenger">Passenger</option>
            <option value="driver">Driver</option>
          </Select>
        </Field>
        <Field
          label="Seats for passengers"
          hint={role === "passenger" ? "Drivers only." : undefined}
        >
          <TextInput
            value={seats}
            inputMode="numeric"
            disabled={role === "passenger"}
            onChange={(e) => setSeats(e.target.value)}
          />
        </Field>
      </div>

      {error && <Problem>{error}</Problem>}

      <div>
        <Button type="submit" disabled={busy || disabled || name.trim() === ""}>
          {busy ? "Adding…" : "Add to roster"}
        </Button>
      </div>
    </form>
  );
}
