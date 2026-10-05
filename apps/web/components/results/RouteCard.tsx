"use client";

/**
 * One car, one leg: who is in it, in what order, and when each of them is collected.
 *
 * "The list decides, the map verifies" (a standing decision) applies to results as much as to the
 * roster -- this is the authoritative rendering of the answer, and it stays complete and readable
 * when the map fails to load.
 */

import type { Participant } from "@/lib/api/participants";
import {
  formatDistance,
  formatDuration,
  legOf,
  stopNumber,
  type LegChoice,
  type Route,
} from "@/lib/api/solutions";
import { routeColor } from "@/lib/results/colors";
import { formatTimeInZone } from "@/lib/time";

import { PinSelect } from "./PinSelect";

export function RouteCard({
  route,
  index,
  leg,
  timeZone,
  drivers,
  pinnedBy,
  onPin,
  pinBusy,
  directionsHref,
  highlighted,
  onHighlight,
}: {
  route: Route;
  index: number;
  leg: LegChoice;
  timeZone: string;
  drivers: Participant[];
  /** Current `pinned_driver_id` per participant, read from the live roster rather than the solution. */
  pinnedBy: Map<string, string | null>;
  onPin: (riderId: string, driverId: string | null) => void;
  pinBusy: boolean;
  /** Null when the driver's home could not be located, so no honest link can be built. */
  directionsHref: string | null;
  highlighted: boolean;
  onHighlight: (routeId: string | null) => void;
}) {
  const color = routeColor(index);
  const stops = legOf(route, leg).stops;

  return (
    // A rule between cars, not a box around each one. Twelve bordered rectangles stacked down a
    // page is furniture; a line is the same division and reads as a timetable. The car's colour is
    // carried by a bar in the left margin, which is also the only thing tying this block to a line
    // on the map, so it wants more presence than the 10px dot it was.
    <article
      onMouseEnter={() => onHighlight(route.id)}
      onMouseLeave={() => onHighlight(null)}
      className={`border-t border-line py-5 pl-4 transition-colors first:border-t-0 ${
        highlighted ? "bg-surface-sunken" : ""
      }`}
      style={{ boxShadow: `inset 3px 0 0 0 ${color}` }}
    >
      <header className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h3 className="font-display text-xl text-ink">{route.driver_name} drives</h3>
        <p className="text-sm tabular-nums text-ink-muted">
          {route.seats_used} {route.seats_used === 1 ? "rider" : "riders"} ·{" "}
          {formatDuration(route.total_duration_s)} · {formatDistance(route.total_distance_m)} ·{" "}
          {route.detour_seconds > 0
            ? `${formatDuration(route.detour_seconds)} out of their way`
            : "no detour"}
        </p>
      </header>

      {/*
        A car with nobody in it is a real and common outcome -- a driver whose own trip no rider was
        on the way of -- but it is the least interesting card on the screen, and as a full-height
        panel saying one sentence it took as much room as a car of four. It collapses to its header
        plus one muted line instead.
      */}
      {stops.length === 0 ? (
        <p className="mt-1 text-sm text-ink-muted">
          {leg === "outbound" ? "No riders on the way there." : "No riders on the way back."}{" "}
          {directionsHref ? (
            <a
              href={directionsHref}
              target="_blank"
              rel="noreferrer noopener"
              className="text-accent underline underline-offset-2"
            >
              Google Maps ↗
            </a>
          ) : (
            // Still worth saying with nobody aboard: this driver is making the trip either way.
            <span>No directions link — this driver has no coordinates on the roster.</span>
          )}
        </p>
      ) : (
        <>
          {/*
            A numbered list set like a timetable: the stop number in a hanging column of its own,
            then the name, with the time flush right where a reader scans for it. Times are the
            text face with `tabular-nums` rather than mono -- lining tabular figures align in a
            column without the typewriter texture.
          */}
          <ol className="mt-3 flex flex-col">
            {stops.map((stop) => (
              <li
                key={stop.participant_id}
                className="flex items-baseline gap-3 py-1.5 transition-colors hover:bg-surface-sunken"
              >
                <span
                  aria-hidden
                  className="w-5 shrink-0 text-right text-sm tabular-nums text-ink-muted"
                  style={{ color }}
                >
                  {stopNumber(stop)}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[15px] text-ink">{stop.display_name}</p>
                  <p className="truncate text-sm text-ink-muted">{stop.pickup_address}</p>
                </div>
                <span className="shrink-0 text-[15px] tabular-nums text-ink">
                  {formatTimeInZone(new Date(stop.eta), timeZone)}
                </span>
                <PinSelect
                  value={pinnedBy.get(stop.participant_id) ?? null}
                  riderId={stop.participant_id}
                  drivers={drivers}
                  onChange={(driverId) => onPin(stop.participant_id, driverId)}
                  disabled={pinBusy}
                />
              </li>
            ))}
          </ol>

          <footer className="mt-3">
            {directionsHref ? (
              <a
                href={directionsHref}
                target="_blank"
                rel="noreferrer noopener"
                className="text-sm text-accent underline underline-offset-2"
              >
                Open this leg in Google Maps ↗
              </a>
            ) : (
              <p className="text-sm text-ink-muted">
                No directions link — someone on this leg has no coordinates on the roster. A link
                that quietly skipped them would send the driver past a house without stopping.
              </p>
            )}
          </footer>
        </>
      )}
    </article>
  );
}
