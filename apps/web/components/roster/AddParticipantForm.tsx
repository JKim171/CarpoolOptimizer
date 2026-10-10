"use client";

/**
 * Add one person.
 *
 * The alternative to the paste path, and the only way in for the rows paste could not resolve: it
 * accepts a pin placed by hand, so a house the geocoder has never heard of is still enterable.
 *
 * **It used to make that claim and not keep it.** The form required a coordinate and offered
 * exactly one way to get one -- picking an autocomplete suggestion -- while the field above it
 * said "you can still place the pin by hand". There was no pin to place: this form has no map, and
 * the canvas beside it only ever drew the roster. So an address the provider's autocomplete does
 * not index, which includes ordinary ones like `1100 Packard St, Ann Arbor`, was a dead end with
 * two contradictory messages on screen. Two things fixed that, and both matter:
 *
 *  - **The pin is real.** `point` is owned by the event page and drawn on the canvas, so a click
 *    on the map places this person's pickup and a drag corrects it.
 *  - **Submitting falls back from autocomplete to search.** They are different endpoints with
 *    different coverage -- `/v1/geocode` finds `500 E Liberty St, Ann Arbor`, which
 *    `/v1/geocode/autocomplete` returns nothing for -- and the paste path has always used the
 *    forgiving one. One lookup per attempt rather than one per keystroke, which is also why this
 *    cannot be what the field does while typing: the search quota is 300 a day for the whole
 *    deployment.
 *
 * The row is written with whatever the lookup returned -- which is the provider's own label on a
 * fresh match, and the typed text on a cache hit, since a cached row deliberately keeps
 * coordinates only (`adapters/geocoding.py`). Either way the roster row and its pin appear
 * together, so a match that landed somewhere unexpected is on screen immediately rather than
 * hidden: "the list decides, the map verifies". Same loop `RosterList` relies on when it resolves
 * an edited address, and the same `resolve` call.
 */

import { useState } from "react";

import { AddressField } from "@/components/AddressField";
import { Button, Field, Problem, Select, TextInput } from "@/components/ui/controls";
import { ApiError } from "@/lib/api/client";
import { resolve, type Place } from "@/lib/api/geocode";
import { addParticipant } from "@/lib/api/participants";

/**
 * The pickup this form is holding, and where it came from.
 *
 * `byHand` is not bookkeeping: it decides whether typing in the address field throws the
 * coordinates away. See the field's `onChange` below -- the two origins want opposite behaviour.
 */
export type DraftPickup = { lat: number; lng: number; byHand: boolean };

export function AddParticipantForm({
  publicId,
  disabled,
  onAdded,
  point,
  onPoint,
}: {
  publicId: string;
  disabled: boolean;
  onAdded: () => void;
  /** Lifted to the event page, which draws it on the canvas and takes clicks for it. */
  point: DraftPickup | null;
  onPoint: (point: DraftPickup | null) => void;
}) {
  const [name, setName] = useState("");
  const [address, setAddress] = useState("");
  const [role, setRole] = useState<"passenger" | "driver">("passenger");
  const [seats, setSeats] = useState("1");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);

    const typed = address.trim();
    if (!typed) {
      // An address is required even with a pin: the pin tells the solver where to go, and the row
      // is what tells a driver where they are going.
      setError(
        point
          ? "Add an address or a note for this pickup, so the row says where it is."
          : "Enter a pickup address, or click the map to place the pin.",
      );
      return;
    }

    setBusy(true);
    try {
      let pickup = point ? { address: typed, lat: point.lat, lng: point.lng } : null;

      if (!pickup) {
        const [resolution] = await resolve([typed]);
        if (!resolution?.place) {
          setError(`No match for “${typed}”. Click the map to place the pin instead.`);
          return;
        }
        pickup = {
          address: resolution.place.address,
          lat: resolution.place.lat,
          lng: resolution.place.lng,
        };
      }

      await addParticipant(publicId, {
        display_name: name.trim(),
        role,
        // A passenger may not hold seats -- the API answers 422, so send the pair it accepts.
        seats_available: role === "driver" ? Math.max(Number.parseInt(seats, 10) || 1, 1) : 0,
        pickup,
        // Required by the generated types: every field carrying a server-side default is stated.
        needs_outbound: true,
        needs_return: true,
        priority: 0,
      });
      setName("");
      setAddress("");
      onPoint(null);
      setRole("passenger");
      setSeats("1");
      onAdded();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not add that person.");
    } finally {
      setBusy(false);
    }
  }

  // `max-w-2xl` rather than filling the panel: at the page's full width a name field runs most of
  // a laptop screen, which reads as a text area and puts the label far from the caret.
  return (
    <form onSubmit={submit} className="flex max-w-2xl flex-col gap-4">
      <Field label="Name">
        <TextInput
          value={name}
          required
          maxLength={120}
          onChange={(e) => setName(e.target.value)}
          placeholder="Ana Ruiz"
        />
      </Field>

      {/* `200 N Main St, Ann Arbor` rather than `12 Oak St, Ann Arbor`, which is a street the
          provider has never heard of: the example in a placeholder is the first thing a new
          organizer types, and it answered "No matches". */}
      <AddressField
        label="Pickup address"
        value={address}
        placeholder="200 N Main St, Ann Arbor"
        resolved={point !== null}
        onChange={(v) => {
          setAddress(v);
          // Typing after *picking a suggestion* invalidates those coordinates: the two must move
          // together, or the row says one thing and the solver routes by another. A pin placed by
          // hand is the opposite case -- there the text is a label for a coordinate that is
          // already right, and typing it is the expected next step -- so that one survives.
          if (point && !point.byHand) onPoint(null);
        }}
        onPick={(place: Place) => {
          setAddress(place.address);
          onPoint({ lat: place.lat, lng: place.lng, byHand: false });
          // The error that sent them to the suggestions has been answered; leaving it up means
          // the form reads as broken while it is in fact ready to submit.
          setError(null);
        }}
      />

      {point?.byHand && (
        <p className="text-xs text-ink-muted">
          Pickup pinned on the map. Drag the pin to adjust it, or{" "}
          <button
            type="button"
            onClick={() => onPoint(null)}
            className="underline underline-offset-2 hover:text-ink"
          >
            remove the pin
          </button>{" "}
          and choose an address instead.
        </p>
      )}

      {/*
        **Stacked, always.** This was `sm:grid-cols-2`, which is the right instinct and the wrong
        mechanism now that the form lives in a rail: Tailwind's breakpoints measure the *viewport*,
        and the viewport being wide is exactly when the rail is at its narrowest relative to it. So
        the pair went to two columns on a desktop -- about 160px each in a 23rem rail, where "Seats
        for passengers" wraps to three lines over a field two digits wide -- and stayed stacked on
        the phone, which is the one width where side-by-side would have been fine. Same correction
        as `ResultSummary` (`48b0a81`): the rail's width is set by the shell, not by the window, so
        the column count is too.
      */}
      <div className="grid gap-3">
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
