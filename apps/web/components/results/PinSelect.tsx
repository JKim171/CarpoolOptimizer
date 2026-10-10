"use client";

/**
 * "This person must ride with that driver."
 *
 * A pin is the organizer's override of the solver: siblings who should travel together, a rider who
 * needs a particular driver's help, a promise already made. It lives on the *rider* as
 * `pinned_driver_id` and survives re-solving, which is the point -- the solver is asked again and
 * has to honour it.
 *
 * Offered here, in the results, rather than only in the roster table, because this is where an
 * organizer forms the opinion. You disagree with an assignment at the moment you read it.
 *
 * The server validates the same rules (an active driver of this event, not the rider themselves);
 * this narrows the options so the common mistakes cannot be made rather than being rejected.
 *
 * **The control never says "pin" to the reader.** `pinned_driver_id` is the field's name and the
 * name this file uses for the concept, but one of these sits on every rider row of a screen whose
 * canvas is a map covered in pins and whose caption reads "drag a pin to correct a pickup point".
 * The same word for a map marker and for a constraint on the solver, eight inches apart, is one
 * word too many. The reader is asked the question instead -- who must this rider travel with --
 * and the unset state answers it: any driver.
 */

import type { Participant } from "@/lib/api/participants";

export function PinSelect({
  value,
  riderId,
  drivers,
  onChange,
  disabled,
}: {
  value: string | null;
  riderId: string;
  drivers: Participant[];
  onChange: (driverId: string | null) => void;
  disabled?: boolean;
}) {
  // A pin naming yourself is rejected by the API, and a rider cannot be their own driver.
  const options = drivers.filter((d) => d.id !== riderId);

  // Borderless until it is pointed at or carries a pin. One of these sits on every rider row, and
  // as a bordered control they became a column of boxes louder than the names they act on -- the
  // same thing that drove the roster table's actions to `ghost`. An unset pin is the common case
  // and says nothing, so it should look like nothing; a set pin is an override of the solver and
  // keeps its outline so it cannot be missed while scanning.
  const pinned = value !== null;

  return (
    <label className="flex shrink-0 items-center text-xs">
      <span className="sr-only">Must ride with</span>
      <select
        value={value ?? ""}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value === "" ? null : e.target.value)}
        className={`max-w-32 truncate rounded-[2px] border px-1.5 py-1 text-xs transition-colors disabled:opacity-50 ${
          pinned
            ? "border-line bg-surface-raised text-ink"
            : "border-transparent bg-transparent text-ink-muted hover:border-line hover:bg-surface-raised"
        }`}
      >
        <option value="">any driver</option>
        {options.map((driver) => (
          <option key={driver.id} value={driver.id}>
            {driver.display_name}
          </option>
        ))}
      </select>
    </label>
  );
}
