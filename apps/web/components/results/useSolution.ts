"use client";

/**
 * Ask for an answer, wait for it, and hold it.
 *
 * **This was the top half of `ResultsPanel`.** It moved out when the map became the app's canvas:
 * the map and the list of cars are now siblings in the shell rather than parent and child, so the
 * state they share -- which solution, which leg, which car is highlighted -- cannot live inside
 * either of them. It belongs to the screen that renders both.
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
  type Solution,
} from "@/lib/api/solutions";
import { directionsUrl, legWaypoints, type Waypoint } from "@/lib/results/googleMaps";

import type { MappedRoute } from "./RouteMap";
import { useHoverHighlight } from "./useHoverHighlight";

export type Venue = { address: string; lat: number; lng: number };

/** Poll cadence. Fast enough that an inline solve feels immediate, slow enough to be unremarkable. */
const POLL_MS = 1000;

export type SolutionState = {
  solution: Solution | undefined;
  routes: Route[];
  /** The same routes resolved to coordinates, for the map. */
  mapped: MappedRoute[];
  /** People in the answer the roster can no longer place -- cancelled since the solve, usually. */
  unplottable: number;
  leg: LegChoice;
  setLeg: (leg: LegChoice) => void;
  highlightedRouteId: string | null;
  setHighlightedRouteId: (routeId: string | null) => void;
  drivers: Participant[];
  pinnedBy: Map<string, string | null>;
  jobDescription: string | undefined;
  jobFailed: boolean;
  conflict: string | null;
  failure: Error | undefined;
  busy: boolean;
  activating: boolean;
  pinBusy: boolean;
  start: () => void;
  activate: () => void;
  pin: (riderId: string, driverId: string | null) => void;
  directionsFor: (route: Route) => string | null;
};

export function useSolution({
  publicId,
  venue,
  people,
  onRosterChanged,
}: {
  publicId: string;
  venue: Venue | null;
  people: Participant[];
  onRosterChanged: () => void;
}): SolutionState {
  const queryClient = useQueryClient();
  const [jobId, setJobId] = useState<string | null>(null);
  const [leg, setLeg] = useState<LegChoice>("outbound");
  const [highlightedRouteId, setHighlightedRouteId] = useHoverHighlight();
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

  return {
    solution: solution.data,
    routes,
    mapped,
    unplottable,
    leg,
    setLeg,
    highlightedRouteId,
    setHighlightedRouteId,
    drivers,
    pinnedBy,
    jobDescription: job.data ? describeJob(job.data) : undefined,
    jobFailed: job.data?.status === "failed",
    conflict,
    failure: [start.error, job.error, solution.error, activate.error, pin.error].find(
      (e): e is Error => e instanceof Error,
    ),
    busy: start.isPending || running,
    activating: activate.isPending,
    pinBusy: pin.isPending,
    start: () => start.mutate(),
    activate: () => activate.mutate(),
    pin: (riderId, driverId) => pin.mutate({ riderId, driverId }),
    directionsFor,
  };
}
