"use client";

/**
 * Pick a theme: follow the machine, or override it.
 *
 * **Three options rather than a two-state switch.** The app followed `prefers-color-scheme` and
 * nothing else, and the dark basemap and the eight route colours were chosen on that basis. A plain
 * light/dark flip would have had to throw that away -- once you touch it, "whatever this machine
 * says" is no longer reachable, and the reader who only wanted to override one screen has silently
 * opted out of ever following their OS again. `Auto` keeps the old behaviour as the default and the
 * other two are an override, which is also why `system` is what an unreadable or absent stored
 * value resolves to.
 *
 * **Real radio inputs, not buttons.** A set of three exclusive options is a radio group, and using
 * the native one means arrow-key navigation, the roving tabstop and the announcement all come from
 * the browser. Hand-rolling `role="radiogroup"` with a keydown handler is how that gets subtly
 * wrong. The inputs are `sr-only` and the `<label>` carries the look; clicking a label activates
 * its input, so nothing needs an `onClick`.
 *
 * Selection is a tint, not grey text for the unselected: `--ink-muted` at this size reads about
 * 4.98:1, which is the defect `Badge` was fixed for (`2c9a555`), and the same answer applies here
 * -- full-strength ink on all three, and the `accent-soft` pair, which clears 7:1, marks the one
 * that is on.
 */

import { useThemePreference, type ThemePreference } from "@/lib/colorScheme";

const OPTIONS: { value: ThemePreference; label: string; hint: string }[] = [
  { value: "system", label: "Auto", hint: "Follow this device" },
  { value: "light", label: "Light", hint: "Always light" },
  { value: "dark", label: "Dark", hint: "Always dark" },
];

export function ThemeToggle() {
  const [preference, setPreference] = useThemePreference();

  return (
    <fieldset className="shrink-0">
      <legend className="sr-only">Theme</legend>
      {/* The hairline goes around the group, not around each option: it is one control. */}
      <div className="flex rounded-[2px] border border-line">
        {OPTIONS.map((option) => {
          const selected = preference === option.value;
          return (
            <label
              key={option.value}
              title={option.hint}
              className={
                "cursor-pointer px-2.5 py-1 text-xs transition-colors " +
                // A rule between options rather than a gap, so the three read as one object.
                "border-l border-line first:border-l-0 " +
                (selected
                  ? "bg-accent-soft font-medium text-accent-soft-ink"
                  : "text-ink hover:bg-surface-sunken")
              }
            >
              {/*
                `sr-only` rather than `appearance-none`: the input still has to be focusable and
                reachable by arrow key, which `hidden` and `display:none` would both break. The
                focus ring lands on the input, which is inside the label, so it outlines the option
                the reader is on -- see the one focus treatment in `globals.css`.
              */}
              <input
                type="radio"
                name="theme"
                value={option.value}
                checked={selected}
                onChange={() => setPreference(option.value)}
                className="sr-only"
              />
              {option.label}
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}
