"use client";

/**
 * The roster, and the place it gets corrected.
 *
 * "The list decides, the map verifies": this list is authoritative, and the map beside it exists
 * to make a bad coordinate visible. Both directions of highlighting are wired up, because a pin in
 * the wrong place is only actionable once you know whose it is.
 *
 * Editing is inline rather than in a dialog. A coordinator fixing a roster is doing a long run of
 * small corrections -- a spelling, a seat count, someone who turns out to be driving -- and a modal
 * per change is what makes the spreadsheet feel faster.
 *
 * **This was a five-column table** (`RosterTable`) while the roster had the full width of a
 * document to sit in. In the shell it lives in a rail about four hundred pixels wide, where five
 * columns means five truncated ones, so each person is now two lines: who they are and what they
 * are on the first, where they are on the second. Nothing was dropped -- name, pickup, role, seats
 * and both actions are all still here -- and none of the editing logic changed.
 *
 * Row actions are revealed on hover to keep a fifty-person list from being a wall of buttons, and
 * are *always* shown below `lg`, where there is no hover and a hidden control is simply missing.
 */

import { useState } from "react";

import { Badge, Button, Problem, Select, TextInput } from "@/components/ui/controls";
import { ApiError } from "@/lib/api/client";
import { resolve } from "@/lib/api/geocode";
import type { Participant, ParticipantPatch } from "@/lib/api/participants";

type Draft = {
  display_name: string;
  address: string;
  role: "driver" | "passenger";
  seats_available: string;
};

const draftOf = (p: Participant): Draft => ({
  display_name: p.display_name,
  address: p.pickup.address,
  role: p.role === "driver" ? "driver" : "passenger",
  seats_available: String(p.seats_available),
});

export function RosterList({
  participants,
  highlightedId,
  onHighlight,
  onPatch,
  onCancel,
  busyId,
}: {
  participants: Participant[];
  highlightedId: string | null;
  onHighlight: (id: string | null) => void;
  onPatch: (id: string, patch: ParticipantPatch) => Promise<void>;
  onCancel: (id: string) => Promise<void>;
  busyId: string | null;
}) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  function startEdit(p: Participant) {
    setEditingId(p.id);
    setDraft(draftOf(p));
    setError(null);
  }

  function stopEdit() {
    setEditingId(null);
    setDraft(null);
    setError(null);
  }

  async function save(person: Participant) {
    if (!draft) return;
    setSaving(true);
    setError(null);
    try {
      const patch: ParticipantPatch = {};

      if (draft.display_name.trim() && draft.display_name !== person.display_name) {
        patch.display_name = draft.display_name.trim();
      }

      const seats = Number.parseInt(draft.seats_available, 10) || 0;
      // The API rejects a passenger holding seats, so send the pair the server will accept rather
      // than a 422 the coordinator has to decode.
      const role = draft.role;
      const normalizedSeats = role === "passenger" ? 0 : Math.max(seats, 1);
      if (role !== person.role) patch.role = role;
      if (normalizedSeats !== person.seats_available) patch.seats_available = normalizedSeats;

      // An address change means new coordinates; sending the typed string with the old lat/lng
      // would leave the row saying one thing and routing by another.
      if (draft.address.trim() && draft.address.trim() !== person.pickup.address) {
        const [resolution] = await resolve([draft.address.trim()]);
        if (!resolution?.place) {
          setError(
            `No match for “${draft.address.trim()}”. Leave the address as it was, or drag the pin instead.`,
          );
          setSaving(false);
          return;
        }
        patch.pickup = {
          address: resolution.place.address,
          lat: resolution.place.lat,
          lng: resolution.place.lng,
        };
      }

      if (Object.keys(patch).length > 0) await onPatch(person.id, patch);
      stopEdit();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not save that change.");
    } finally {
      setSaving(false);
    }
  }

  if (participants.length === 0) {
    return (
      <p className="text-sm text-ink-muted">
        No one on the roster yet. Paste a list below, or add someone individually.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      {error && <Problem>{error}</Problem>}

      <ul className="-mx-2 divide-y divide-line border-y border-line">
        {participants.map((person) => {
          const editing = editingId === person.id;
          const busy = busyId === person.id;

          return (
            <li
              key={person.id}
              onMouseEnter={() => onHighlight(person.id)}
              onMouseLeave={() => onHighlight(null)}
              onFocus={() => onHighlight(person.id)}
              className={`group px-2 transition-colors ${
                highlightedId === person.id ? "bg-surface-sunken" : "hover:bg-surface-sunken"
              }`}
            >
              {editing && draft ? (
                <div className="flex flex-col gap-2 py-3">
                  <TextInput
                    value={draft.display_name}
                    aria-label="Name"
                    onChange={(e) => setDraft({ ...draft, display_name: e.target.value })}
                  />
                  <TextInput
                    value={draft.address}
                    aria-label="Pickup address"
                    onChange={(e) => setDraft({ ...draft, address: e.target.value })}
                  />
                  <div className="grid grid-cols-2 gap-2">
                    <Select
                      value={draft.role}
                      aria-label="Role"
                      onChange={(e) =>
                        setDraft({ ...draft, role: e.target.value as Draft["role"] })
                      }
                    >
                      <option value="passenger">Passenger</option>
                      <option value="driver">Driver</option>
                    </Select>
                    <TextInput
                      value={draft.seats_available}
                      inputMode="numeric"
                      aria-label="Seats available"
                      disabled={draft.role === "passenger"}
                      onChange={(e) => setDraft({ ...draft, seats_available: e.target.value })}
                    />
                  </div>
                  <div className="flex gap-2">
                    <Button type="button" onClick={() => save(person)} disabled={saving}>
                      {saving ? "Saving…" : "Save"}
                    </Button>
                    <Button type="button" variant="quiet" onClick={stopEdit} disabled={saving}>
                      Cancel
                    </Button>
                  </div>
                </div>
              ) : (
                <div className="py-2">
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="truncate text-[15px] text-ink">{person.display_name}</span>
                    {/*
                      Who can drive is the one thing this list is consulted for -- it decides
                      whether a roster can be solved at all. Only the driver is badged: a chip on
                      all twelve rows is a second column of decoration, and "passenger" is the
                      default this product assumes.
                    */}
                    {person.role === "driver" && (
                      <span className="flex shrink-0 items-center gap-1.5">
                        <Badge tone="accent">Driver</Badge>
                        <span className="text-sm tabular-nums text-ink-muted">
                          {person.seats_available}
                        </span>
                      </span>
                    )}
                  </div>
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="truncate text-sm text-ink-muted">{person.pickup.address}</span>
                    <span className="flex shrink-0 opacity-0 transition-opacity group-focus-within:opacity-100 group-hover:opacity-100 max-lg:opacity-100">
                      <Button type="button" variant="ghost" onClick={() => startEdit(person)}>
                        Edit
                      </Button>
                      <Button
                        type="button"
                        variant="ghost"
                        disabled={busy}
                        onClick={() => onCancel(person.id)}
                      >
                        {busy ? "Removing…" : "Remove"}
                      </Button>
                    </span>
                  </div>
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
