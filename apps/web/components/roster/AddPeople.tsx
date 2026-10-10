"use client";

/**
 * The two ways a roster gets entered, as two tabs rather than two stacked blocks.
 *
 * **What was wrong with stacking them.** Both paths lived in one "Add people" section, paste
 * first, with nothing between them: a `Paste a roster` label, a textarea, a Preview button, and
 * then straight into `Name`, `Pickup address`, `Role`, `Seats`. Every one of those labels is the
 * same `text-sm font-medium`, because they *are* all field labels, so there was no level between
 * the section heading and the fields and the whole thing read as a single form whose first field
 * happened to be a paste box -- with "Add to roster" as its submit. The reported experience was
 * exactly that: that pasting from a spreadsheet looked compulsory. Hitting Preview made it worse,
 * since the preview table pushes the single-person form a few hundred pixels further down a rail
 * that is already scrolling.
 *
 * **Why tabs rather than reordering.** Paste is the primary path by decision, not by accident --
 * a coordinator arrives with the roster already in Sheets, and a form that takes forty names one
 * at a time is slower than the status quo they are being asked to leave (see `PasteRoster`). So
 * the fix cannot be to demote it. Tabs say "two ways to do this, pick one" without ranking them
 * by vertical position at all, and they bound the section's height, which the stacked version
 * could not.
 *
 * **Both panels stay mounted**, hidden with the `hidden` attribute rather than unmounted. A
 * half-typed person or an unimported paste must survive a glance at the other tab; `hidden` also
 * takes the inert panel out of the tab order and the accessibility tree, so nothing is reachable
 * that is not visible. It needs a plain wrapper to work -- the attribute's `display:none` loses to
 * any Tailwind display utility, and both panels are flex containers.
 *
 * **A radio group, not a hand-rolled tablist.** Same reasoning as `ThemeToggle`: two exclusive
 * options are what radios are, and the native ones bring arrow-key navigation, the roving tabstop
 * and the announcement with them. A `role="tab"` implementation would owe a keydown handler, and
 * that is the part that gets subtly wrong.
 */

import type { ReactNode } from "react";

import { AddParticipantForm, type DraftPickup } from "@/components/roster/AddParticipantForm";
import { PasteRoster } from "@/components/roster/PasteRoster";

export type AddMode = "paste" | "one";

const TABS: { value: AddMode; label: string }[] = [
  { value: "paste", label: "Paste a list" },
  { value: "one", label: "One at a time" },
];

export function AddPeople({
  publicId,
  seatsLeft,
  onChanged,
  mode,
  onMode,
  pickup,
  onPickup,
}: {
  publicId: string;
  seatsLeft: number;
  onChanged: () => void;
  mode: AddMode;
  onMode: (mode: AddMode) => void;
  /** Held by the event page, because the canvas is where it is placed and drawn. */
  pickup: DraftPickup | null;
  onPickup: (pickup: DraftPickup | null) => void;
}) {
  return (
    <div className="flex flex-col gap-4">
      <fieldset>
        <legend className="sr-only">How to add people</legend>
        {/* The hairline goes around the pair, not around each option: it is one control. */}
        <div className="flex rounded-[2px] border border-line">
          {TABS.map((tab) => {
            const selected = mode === tab.value;
            return (
              <label
                key={tab.value}
                className={
                  "flex-1 cursor-pointer px-3 py-1.5 text-center text-sm transition-colors " +
                  "border-l border-line first:border-l-0 " +
                  (selected
                    ? "bg-accent-soft font-medium text-accent-soft-ink"
                    : "text-ink hover:bg-surface-sunken")
                }
              >
                <input
                  type="radio"
                  name="add-people"
                  value={tab.value}
                  checked={selected}
                  onChange={() => onMode(tab.value)}
                  className="sr-only"
                />
                {tab.label}
              </label>
            );
          })}
        </div>
      </fieldset>

      <Panel hidden={mode !== "paste"}>
        <PasteRoster publicId={publicId} seatsLeft={seatsLeft} onImported={onChanged} />
      </Panel>

      <Panel hidden={mode !== "one"}>
        <AddParticipantForm
          publicId={publicId}
          disabled={seatsLeft === 0}
          onAdded={onChanged}
          point={pickup}
          onPoint={onPickup}
        />
      </Panel>
    </div>
  );
}

/** A bare wrapper, so `hidden` is not overridden by a display utility on the panel itself. */
function Panel({ hidden, children }: { hidden: boolean; children: ReactNode }) {
  return <div hidden={hidden}>{children}</div>;
}
