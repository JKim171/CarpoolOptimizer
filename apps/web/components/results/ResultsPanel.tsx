"use client";

/**
 * Ask for an answer, wait for it, and show it.
 *
 * Written against the async contract -- enqueue, poll, read the solution -- even though the API
 * solves inline today and the first response already carries a finished job. That is the seam a
 * separate worker slots into (docs/design.md 4.2), and polling a job that is already `succeeded`
 * costs one request.
 *
 * The coordinates are joined in here rather than served with the solution: `StopRead` carries a
 * participant id, a name, an ETA and an address, but no lat/lng, because a solution records an
 * *ordering* and times are derived (CLAUDE.md). The roster is the source of position. That join can
 * miss -- someone cancelled since the solve still appears in it -- and where it misses this reports
 * the gap rather than quietly plotting fewer pins than there are people.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { Button, Problem } from "@/components/ui/controls";
import { ApiError } from "@/lib/api/client";
import {
  describeJob,
  fetchJob,
  isTerminal,
  jobKeys,
  startOptimization,
  type Job,
} from "@/lib/api/optimizations";
import { isLocated, patchParticipant, type Participant } from "@/lib/api/participants";
import {
  activateSolution,
  fetchSolution,
  legOf,
  stopNumber,
  solutionKeys,
  type LegChoice,
  type Route,
} from "@/lib/api/solutions";
import { directionsUrl, legWaypoints, type Waypoint } from "@/lib/results/googleMaps";

import { RouteCard } from "./RouteCard";
import { RouteMap, type MappedRoute } from "./RouteMap";
import { UnassignedList } from "./UnassignedList";

export type Venue = { address: string; lat: number; lng: number };

/** Poll cadence. Fast enough that an inline solve feels immediate, slow enough to be unremarkable. */
const POLL_MS = 1000;

export function ResultsPanel({
  publicId,
  venue,
  timeZone,
  people,
  onRosterChanged,
}: {
  publicId: string;
  venue: Venue | null;
  timeZone: string;
  people: Participant[];
  onRosterChanged: () => void;
}) {
  const queryClient = useQueryClient();
  const [jobId, setJobId] = useState<string | null>(null);
  const [leg, setLeg] = useState<LegChoice>("outbound");
  const [highlightedRouteId, setHighlightedRouteId] = useState<string | null>(null);
  const [conflict, setConflict] = useState<string | null>(null);

  const start = useMutation({
    mutationFn: () => startOptimization(publicId),
    onSuccess: (result) => {
      if (result.kind === "job") {
        setConflict(null);
        setJobId(result.job.job_id);
        // The POST body is a full job read; seeding it means the first poll is not a wasted round
        // trip, and the status line has something to say immediately.
        queryClient.setQueryData(jobKeys.detail(publicId, result.job.job_id), result.job);
        return;
      }
      // 409: another job is already in flight. Poll that one rather than retrying -- a retry hits
      // the same partial unique index and fails identically.
      setConflict(result.detail);
      if (result.existingJobId) setJobId(result.existingJobId);
    },
  });

  const job = useQuery({
    queryKey: jobKeys.detail(publicId, jobId ?? "none"),
    queryFn: () => fetchJob(publicId, jobId as string),
    enabled: jobId !== null,
    refetchInterval: (query) => {
      const current = query.state.data as Job | undefined;
      return current && isTerminal(current.status) ? false : POLL_MS;
    },
  });

  const solutionId = job.data?.solution_id ?? null;
  const solution = useQuery({
    queryKey: solutionKeys.detail(publicId, solutionId ?? "none"),
    queryFn: () => fetchSolution(publicId, solutionId as string),
    enabled: solutionId !== null,
  });

  const activate = useMutation({
    mutationFn: () => activateSolution(publicId, solutionId as string),
    onSuccess: (updated) =>
      queryClient.setQueryData(solutionKeys.detail(publicId, updated.id), updated),
  });

  const pin = useMutation({
    mutationFn: ({ riderId, driverId }: { riderId: string; driverId: string | null }) =>
      patchParticipant(publicId, riderId, { pinned_driver_id: driverId }),
    onSuccess: () => {
      // A pin is part of the problem, so it changes the fingerprint and the roster version: the
      // solution on screen is now describing a question nobody asked. Refetching is what makes the
      // "no longer current" banner appear, which is the prompt to re-optimize.
      onRosterChanged();
      if (solutionId) {
        void queryClient.invalidateQueries({
          queryKey: solutionKeys.detail(publicId, solutionId),
        });
      }
    },
  });

  const byId = useMemo(() => new Map(people.map((p) => [p.id, p])), [people]);
  /** Pin targets: anyone who might drive. A passenger cannot be pinned to, and neither can oneself. */
  const drivers = useMemo(() => people.filter((p) => p.role !== "passenger"), [people]);
  const pinnedBy = useMemo(
    () => new Map(people.map((p) => [p.id, p.pinned_driver_id ?? null])),
    [people],
  );

  const locate = useMemo(() => {
    return (participantId: string): Waypoint | null => {
      const person = byId.get(participantId);
      return person && isLocated(person)
        ? { lat: person.pickup.lat, lng: person.pickup.lng }
        : null;
    };
  }, [byId]);

  const routes = useMemo(() => solution.data?.routes ?? [], [solution.data]);

  const mapped: MappedRoute[] = useMemo(
    () =>
      routes.map((route) => ({
        routeId: route.id,
        driverName: route.driver_name,
        home: locate(route.driver_participant_id),
        stops: legOf(route, leg).stops.flatMap((stop) => {
          const at = locate(stop.participant_id);
          return at ? [{ number: stopNumber(stop), label: stop.display_name, ...at }] : [];
        }),
      })),
    [routes, leg, locate],
  );

  /** People in the answer the roster can no longer place -- cancelled since the solve, usually. */
  const unplottable = useMemo(() => {
    const inSolution = routes.reduce((n, route) => n + legOf(route, leg).stops.length, 0);
    const plotted = mapped.reduce((n, route) => n + route.stops.length, 0);
    return inSolution - plotted;
  }, [routes, mapped, leg]);

  /**
   * A driver's leg as a Google Maps link, or null when it cannot be built honestly. Missing one
   * stop's coordinates means no link at all: a link silently short of a stop would route a driver
   * straight past somebody's house.
   */
  function directionsFor(route: Route): string | null {
    const driverHome = locate(route.driver_participant_id);
    const stops = legOf(route, leg).stops.map((stop) => locate(stop.participant_id));
    if (!driverHome || !venue || stops.some((s) => s === null)) return null;
    try {
      return directionsUrl(legWaypoints({ leg, driverHome, venue, stops: stops as Waypoint[] }));
    } catch {
      // A leg longer than the URL format carries. Better no link than a truncated one.
      return null;
    }
  }

  const running = job.data !== undefined && !isTerminal(job.data.status);
  const busy = start.isPending || running;
  const failure = [start.error, job.error, solution.error, activate.error, pin.error].find(
    (e): e is Error => e instanceof Error,
  );

  return (
    <section className="flex flex-col gap-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-sm font-medium text-ink">Who drives whom</h2>
        <div className="flex items-center gap-3">
          {job.data && <span className="text-xs text-ink-muted">{describeJob(job.data)}</span>}
          <Button onClick={() => start.mutate()} disabled={busy || people.length === 0}>
            {solution.data ? "Re-optimize" : "Work out the carpools"}
          </Button>
        </div>
      </div>

      {people.length === 0 && (
        <p className="text-sm text-ink-muted">Add people to the roster first.</p>
      )}

      {conflict && <Problem>{conflict}</Problem>}

      {failure && (
        <Problem>
          {failure instanceof ApiError ? failure.message : "Something went wrong working that out."}
        </Problem>
      )}

      {job.data?.status === "failed" && !failure && <Problem>{describeJob(job.data)}</Problem>}

      {solution.data && (
        <>
          {solution.data.is_stale && (
            <p className="rounded-md bg-warn-surface px-3 py-2 text-sm text-warn-ink">
              The roster has changed since this was worked out, so it is a real arrangement but not
              the current one. Re-optimize to bring it up to date — or activate it anyway if you
              prefer it.
            </p>
          )}

          <div className="flex flex-wrap items-center justify-between gap-2">
            <div
              role="group"
              aria-label="Which leg to show"
              className="inline-flex overflow-hidden rounded-md border border-line"
            >
              {(["outbound", "inbound"] as const).map((choice) => (
                <button
                  key={choice}
                  type="button"
                  onClick={() => setLeg(choice)}
                  aria-pressed={leg === choice}
                  className={`px-3 py-1.5 text-xs font-medium ${
                    leg === choice
                      ? "bg-accent text-accent-ink"
                      : "bg-surface-raised text-ink hover:bg-surface-sunken"
                  }`}
                >
                  {choice === "outbound" ? "There" : "Back"}
                </button>
              ))}
            </div>

            {solution.data.is_active ? (
              <span className="text-xs text-ink-muted">This is the active plan.</span>
            ) : (
              <Button
                variant="quiet"
                onClick={() => activate.mutate()}
                disabled={activate.isPending}
              >
                Make this the plan
              </Button>
            )}
          </div>

          {unplottable > 0 && (
            <p className="text-sm text-warn-ink">
              {unplottable} {unplottable === 1 ? "stop is" : "stops are"} missing from the map:{" "}
              {unplottable === 1 ? "that person is" : "those people are"} no longer on the roster.
              They are still listed below.
            </p>
          )}

          <RouteMap
            routes={mapped}
            venue={venue}
            leg={leg}
            highlightedRouteId={highlightedRouteId}
          />

          <div className="flex flex-col gap-3">
            {routes.map((route, index) => (
              <RouteCard
                key={route.id}
                route={route}
                index={index}
                leg={leg}
                timeZone={timeZone}
                drivers={drivers}
                pinnedBy={pinnedBy}
                onPin={(riderId, driverId) => pin.mutate({ riderId, driverId })}
                pinBusy={pin.isPending}
                directionsHref={directionsFor(route)}
                highlighted={highlightedRouteId === route.id}
                onHighlight={setHighlightedRouteId}
              />
            ))}
          </div>

          <UnassignedList
            unassigned={solution.data.unassigned}
            drivers={drivers}
            pinnedBy={pinnedBy}
            onPin={(riderId, driverId) => pin.mutate({ riderId, driverId })}
            pinBusy={pin.isPending}
          />

          {routes.length === 0 && solution.data.unassigned.length > 0 && (
            <p className="text-sm text-ink-muted">
              No cars were formed. Nobody on this roster is marked as driving, or no driver has a
              free seat.
            </p>
          )}
        </>
      )}
    </section>
  );
}
