"use client";

/**
 * The answer, as a list: a summary, one card per car, and whoever is left over.
 *
 * **The map used to be in here.** It is now the shell's canvas, a sibling rather than a child, and
 * the state the two share lives in `useSolution`. What is left is the half you read -- which is
 * what the rail is for, and why this is a column of text with no element in it that wants to be
 * bigger than the column.
 *
 * The leg switch and the activate button stayed with the list rather than moving onto the map.
 * Both change what the *answer* is rather than how it is drawn, and a control floating over a map
 * reads as a map control.
 */

import { Button, Notice, Problem } from "@/components/ui/controls";
import { ApiError } from "@/lib/api/client";

import { ResultSummary } from "./ResultSummary";
import { RouteCard } from "./RouteCard";
import { UnassignedList } from "./UnassignedList";
import type { SolutionState } from "./useSolution";

export type { Venue } from "./useSolution";

export function ResultsPanel({
  solve,
  timeZone,
  rosterSize,
}: {
  solve: SolutionState;
  timeZone: string;
  rosterSize: number;
}) {
  return (
    <div className="flex flex-col gap-4">
      {rosterSize === 0 && (
        <p className="text-[15px] text-ink-muted">Add people to the roster first.</p>
      )}

      {solve.conflict && <Problem>{solve.conflict}</Problem>}

      {solve.failure && (
        <Problem>
          {solve.failure instanceof ApiError
            ? solve.failure.message
            : "Something went wrong working that out."}
        </Problem>
      )}

      {solve.jobFailed && !solve.failure && solve.jobDescription && (
        <Problem>{solve.jobDescription}</Problem>
      )}

      {solve.solution && (
        <>
          {solve.solution.is_stale && (
            <Notice>
              The roster has changed since this was worked out, so it is a real arrangement but not
              the current one. Re-optimize to bring it up to date — or activate it anyway if you
              prefer it.
            </Notice>
          )}

          <div className="flex flex-wrap items-center justify-between gap-2">
            <div
              role="group"
              aria-label="Which leg to show"
              className="inline-flex overflow-hidden rounded-[2px] border border-line-strong"
            >
              {(["outbound", "inbound"] as const).map((choice) => (
                <button
                  key={choice}
                  type="button"
                  onClick={() => solve.setLeg(choice)}
                  aria-pressed={solve.leg === choice}
                  className={`px-4 py-1.5 text-sm transition-colors ${
                    solve.leg === choice
                      ? "bg-accent text-accent-ink"
                      : "text-ink hover:bg-surface-sunken"
                  }`}
                >
                  {choice === "outbound" ? "There" : "Back"}
                </button>
              ))}
            </div>

            {solve.solution.is_active ? (
              <span className="text-sm italic text-ink-muted">This is the active plan.</span>
            ) : (
              <Button variant="quiet" onClick={solve.activate} disabled={solve.activating}>
                Make this the plan
              </Button>
            )}
          </div>

          {solve.unplottable > 0 && (
            <Notice>
              {solve.unplottable} {solve.unplottable === 1 ? "stop is" : "stops are"} missing from
              the map: {solve.unplottable === 1 ? "that person is" : "those people are"} no longer
              on the roster. They are still listed below.
            </Notice>
          )}

          <ResultSummary routes={solve.routes} unassigned={solve.solution.unassigned} />

          <div className="flex flex-col">
            {solve.routes.map((route, index) => (
              <RouteCard
                key={route.id}
                route={route}
                index={index}
                leg={solve.leg}
                timeZone={timeZone}
                drivers={solve.drivers}
                pinnedBy={solve.pinnedBy}
                onPin={solve.pin}
                pinBusy={solve.pinBusy}
                directionsHref={solve.directionsFor(route)}
                highlighted={solve.highlightedRouteId === route.id}
                onHighlight={solve.setHighlightedRouteId}
              />
            ))}
          </div>

          <UnassignedList
            unassigned={solve.solution.unassigned}
            drivers={solve.drivers}
            pinnedBy={solve.pinnedBy}
            onPin={solve.pin}
            pinBusy={solve.pinBusy}
          />

          {solve.routes.length === 0 && solve.solution.unassigned.length > 0 && (
            <p className="text-[15px] text-ink-muted">
              No cars were formed. Nobody on this roster is marked as driving, or no driver has a
              free seat.
            </p>
          )}
        </>
      )}
    </div>
  );
}
