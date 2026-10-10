/**
 * There or back: which leg the cards and the map are showing.
 *
 * Shared by the results panel and the example at `/demo`, so the one control reads the same in
 * both places.
 */

import type { LegChoice } from "@/lib/api/solutions";

export function LegSwitch({ leg, onLeg }: { leg: LegChoice; onLeg: (leg: LegChoice) => void }) {
  return (
    <div
      role="group"
      aria-label="Which leg to show"
      className="inline-flex overflow-hidden rounded-[2px] border border-line-strong"
    >
      {(["outbound", "inbound"] as const).map((choice) => (
        <button
          key={choice}
          type="button"
          onClick={() => onLeg(choice)}
          aria-pressed={leg === choice}
          className={`px-4 py-1.5 text-sm transition-colors ${
            leg === choice ? "bg-accent text-accent-ink" : "text-ink hover:bg-surface-sunken"
          }`}
        >
          {choice === "outbound" ? "There" : "Back"}
        </button>
      ))}
    </div>
  );
}
