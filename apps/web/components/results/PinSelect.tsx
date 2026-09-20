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

  return (
    <label className="flex items-center gap-1.5 text-xs text-ink-muted">
      <span className="sr-only sm:not-sr-only">Pin to</span>
      <select
        value={value ?? ""}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value === "" ? null : e.target.value)}
        className="rounded border border-line bg-surface-raised px-1.5 py-1 text-xs text-ink hover:border-line-strong disabled:opacity-50"
      >
        <option value="">no pin</option>
        {options.map((driver) => (
          <option key={driver.id} value={driver.id}>
            {driver.display_name}
          </option>
        ))}
      </select>
    </label>
  );
}
