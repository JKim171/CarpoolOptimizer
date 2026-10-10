"use client";

/**
 * Address entry with suggestions.
 *
 * Autocomplete fires per keystroke against a provider limited to 100 calls a minute and 3,000 a
 * day, so it is debounced and requires a few characters first (docs/design.md 4.4). The quota is
 * shared by the whole deployment: a tight loop here degrades roster entry for every event.
 *
 * Choosing a suggestion sets both the address and its coordinates together. They must move as a
 * unit -- an address paired with someone else's coordinates is the silent failure that distorts a
 * whole solve, and it is why the API takes `destination` as a nested object rather than three
 * sibling fields (docs/design.md 5.2).
 *
 * **The fallback messages name a real escape hatch, and that is a constraint on the screens that
 * use this.** Autocomplete misses ordinary addresses -- `500 E Liberty St, Ann Arbor` and
 * `1100 Packard St, Ann Arbor` both return nothing from the provider -- so "no matches" is a state
 * a coordinator reaches by typing their own street correctly, not by making a mistake. Every map
 * this field sits beside therefore accepts a click to place the pin, and these messages say so.
 * Do not mount it next to a map that does not.
 */

import { useEffect, useRef, useState } from "react";

import { Field, TextInput } from "@/components/ui/controls";
import { ApiError } from "@/lib/api/client";
import { MIN_QUERY, type Place, suggest } from "@/lib/api/geocode";

const DEBOUNCE_MS = 300;

export function AddressField({
  value,
  onChange,
  onPick,
  label,
  placeholder,
  resolved = false,
}: {
  value: string;
  onChange: (value: string) => void;
  onPick: (place: Place) => void;
  label: string;
  placeholder?: string;
  /**
   * The caller already holds a coordinate for this address, placed on the map.
   *
   * Every note this field writes tells the reader to go and do that, so once they have, the notes
   * are advice for a problem that no longer exists -- and "No matches. Click the map to place the
   * pin instead." directly under "Pickup pinned on the map" reads as a rejection of the pin. The
   * suggestions still appear and picking one still replaces the coordinate; only the nagging goes.
   */
  resolved?: boolean;
}) {
  const [places, setPlaces] = useState<Place[]>([]);
  const [open, setOpen] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  // Bumped on every keystroke so a slow response for an earlier query cannot overwrite the
  // suggestions for a later one.
  const generation = useRef(0);

  useEffect(() => {
    const query = value.trim();
    const mine = ++generation.current;

    // Every state update happens inside the timer rather than in the effect body, short query
    // included. Clearing synchronously here would re-render on each keystroke before the debounce
    // has decided anything.
    const timer = setTimeout(async () => {
      if (query.length < MIN_QUERY) {
        setPlaces([]);
        setNote(null);
        return;
      }
      try {
        const found = await suggest(query);
        if (mine !== generation.current) return;
        setPlaces(found);
        setNote(found.length === 0 ? "No matches. Click the map to place the pin instead." : null);
      } catch (error) {
        if (mine !== generation.current) return;
        setPlaces([]);
        // A geocoder outage must not block event creation: coordinates can always be supplied by
        // dragging the pin (docs/design.md 5.2).
        setNote(
          error instanceof ApiError && error.status === 503
            ? "Address lookup is unavailable. Click the map to place the pin."
            : "Address lookup failed. Click the map to place the pin.",
        );
      }
    }, DEBOUNCE_MS);

    return () => clearTimeout(timer);
  }, [value]);

  // Derived rather than stored: the note is what the *lookup* found, and `resolved` is whether the
  // caller still needs to hear it. Keeping them separate means the pin can be placed before or
  // after the lookup and the result is the same, with no second effect to reconcile them -- and
  // removing the pin brings the note back, which is right, because the advice applies again.
  const shown = resolved ? null : note;

  return (
    <div className="relative">
      <Field label={label} hint={shown}>
        <TextInput
          value={value}
          placeholder={placeholder}
          autoComplete="off"
          onChange={(event) => {
            onChange(event.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          // A click on a suggestion blurs the input first, so closing is deferred past the click.
          onBlur={() => setTimeout(() => setOpen(false), 150)}
        />
      </Field>

      {open && places.length > 0 && (
        <ul className="absolute z-10 mt-1 w-full overflow-hidden rounded-[2px] border border-line-strong bg-surface shadow-lg">
          {places.map((place, index) => (
            <li key={`${place.address}-${index}`}>
              <button
                type="button"
                className="block w-full px-3 py-2 text-left text-sm text-ink hover:bg-surface-sunken"
                onClick={() => {
                  onPick(place);
                  setOpen(false);
                }}
              >
                {place.address}
                {place.is_approximate && (
                  <span className="ml-2 text-xs text-warn-ink">approximate</span>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
