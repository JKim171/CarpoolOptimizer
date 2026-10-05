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
    // The one block on the page that keeps a fill. Everything else gave up its box, but this has to
    // be found by someone skimming past four cars that worked, and on paper that is what a tinted
    // panel is for.
    <section className="border-l-2 border-warn-line bg-warn-surface p-5">
      <h3 className="font-display text-lg text-warn-ink">
        {unassigned.length} {unassigned.length === 1 ? "person has" : "people have"} no ride
      </h3>
      <ul className="mt-3 flex flex-col gap-2.5">
        {unassigned.map((person) => (
          <li key={person.participant_id} className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <span className="text-[15px] text-ink">{person.display_name}</span>
            <span className="flex-1 text-sm text-ink-muted">
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
