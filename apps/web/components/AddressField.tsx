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
 */

import { useEffect, useRef, useState } from "react";

import { ApiError } from "@/lib/api/client";
import { MIN_QUERY, type Place, suggest } from "@/lib/api/geocode";

const DEBOUNCE_MS = 300;

export function AddressField({
  value,
  onChange,
  onPick,
  label,
  placeholder,
}: {
  value: string;
  onChange: (value: string) => void;
  onPick: (place: Place) => void;
  label: string;
  placeholder?: string;
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
        setNote(found.length === 0 ? "No matches. You can still place the pin by hand." : null);
      } catch (error) {
        if (mine !== generation.current) return;
        setPlaces([]);
        // A geocoder outage must not block event creation: coordinates can always be supplied by
        // dragging the pin (docs/design.md 5.2).
        setNote(
          error instanceof ApiError && error.status === 503
            ? "Address lookup is unavailable. Place the pin on the map instead."
            : "Address lookup failed. Place the pin on the map instead.",
        );
      }
    }, DEBOUNCE_MS);

    return () => clearTimeout(timer);
  }, [value]);

  return (
    <div className="relative">
      <label className="block text-sm font-medium">
        {label}
        <input
          className="mt-1 w-full rounded-md border border-black/15 bg-transparent px-3 py-2 text-sm dark:border-white/20"
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
      </label>

      {note && <p className="mt-1 text-xs opacity-60">{note}</p>}

      {open && places.length > 0 && (
        <ul className="absolute z-10 mt-1 w-full overflow-hidden rounded-md border border-black/15 bg-white shadow-lg dark:border-white/20 dark:bg-neutral-900">
          {places.map((place, index) => (
            <li key={`${place.address}-${index}`}>
              <button
                type="button"
                className="block w-full px-3 py-2 text-left text-sm hover:bg-black/5 dark:hover:bg-white/10"
                onClick={() => {
                  onPick(place);
                  setOpen(false);
                }}
              >
                {place.address}
                {place.is_approximate && (
                  <span className="ml-2 text-xs text-amber-700 dark:text-amber-400">
                    approximate
                  </span>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
