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
    <article
      onMouseEnter={() => onHighlight(route.id)}
      onMouseLeave={() => onHighlight(null)}
      className={`rounded-md border bg-surface-raised p-4 transition-colors ${
        highlighted ? "border-line-strong" : "border-line"
      }`}
    >
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="flex items-center gap-2 text-sm font-medium text-ink">
          <span
            aria-hidden
            className="inline-block h-3 w-3 shrink-0 rounded-full"
            style={{ background: color }}
          />
          {route.driver_name} drives
        </h3>
        <p className="text-xs text-ink-muted">
          {route.seats_used} {route.seats_used === 1 ? "rider" : "riders"} ·{" "}
          {formatDuration(route.total_duration_s)} · {formatDistance(route.total_distance_m)} ·{" "}
          {route.detour_seconds > 0
            ? `${formatDuration(route.detour_seconds)} out of their way`
            : "no detour"}
        </p>
      </header>

      {stops.length === 0 ? (
        <p className="mt-3 text-sm text-ink-muted">
          {leg === "outbound" ? "No riders on the way there." : "No riders on the way back."}
        </p>
      ) : (
        <ol className="mt-3 flex flex-col gap-2">
          {stops.map((stop) => (
            <li key={stop.participant_id} className="flex items-start gap-3">
              <span
                aria-hidden
                className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold text-white"
                style={{ background: color }}
              >
                {stopNumber(stop)}
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-sm text-ink">
                  {stop.display_name}
                  <span className="ml-2 font-mono text-xs text-ink-muted">
                    {formatTimeInZone(new Date(stop.eta), timeZone)}
                  </span>
                </p>
                <p className="truncate text-xs text-ink-muted">{stop.pickup_address}</p>
              </div>
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
      )}

      <footer className="mt-3">
        {directionsHref ? (
          <a
            href={directionsHref}
            target="_blank"
            rel="noreferrer noopener"
            className="text-xs text-accent hover:underline"
          >
            Open this leg in Google Maps ↗
          </a>
        ) : (
          <p className="text-xs text-ink-muted">
            No directions link — someone on this leg has no coordinates on the roster. A link that
            quietly skipped them would send the driver past a house without stopping.
          </p>
        )}
      </footer>
    </article>
  );
}
