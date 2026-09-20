"use client";

/**
 * The people no car took.
 *
 * Shown as prominently as the routes, never folded away: a solution that seats most of the roster
 * and quietly drops three people is the single worst thing this product could do, because the
 * organizer's own answer -- the spreadsheet -- never loses anybody. Each row carries the binding
 * reason, which the domain diagnoses by relaxation and orders so the most actionable one wins.
 */

import type { Participant } from "@/lib/api/participants";
import { describeUnassigned, type Unassigned } from "@/lib/api/solutions";

import { PinSelect } from "./PinSelect";

export function UnassignedList({
  unassigned,
  drivers,
  pinnedBy,
  onPin,
  pinBusy,
}: {
  unassigned: Unassigned[];
  drivers: Participant[];
  pinnedBy: Map<string, string | null>;
  onPin: (riderId: string, driverId: string | null) => void;
  pinBusy: boolean;
}) {
  if (unassigned.length === 0) return null;

  return (
    <section className="rounded-md border border-warn-line bg-warn-surface p-4">
      <h3 className="text-sm font-medium text-warn-ink">
        {unassigned.length} {unassigned.length === 1 ? "person has" : "people have"} no ride
      </h3>
      <ul className="mt-3 flex flex-col gap-2">
        {unassigned.map((person) => (
          <li key={person.participant_id} className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <span className="text-sm text-ink">{person.display_name}</span>
            <span className="flex-1 text-xs text-ink-muted">
              {describeUnassigned(person.reason)}
            </span>
            <PinSelect
              value={pinnedBy.get(person.participant_id) ?? null}
              riderId={person.participant_id}
              drivers={drivers}
              onChange={(driverId) => onPin(person.participant_id, driverId)}
              disabled={pinBusy}
            />
          </li>
        ))}
      </ul>
    </section>
  );
}
