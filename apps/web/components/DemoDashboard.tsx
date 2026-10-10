"use client";

/**
 * The example at `/demo`: a finished answer for a made-up club, with nothing to type.
 *
 * It exists because the real thing asks for everyone's home address before it shows anything, and
 * a coordinator who has not decided to trust the site yet will not give it forty of them. This is
 * the same results screen -- the same cards, summary and map, fed a solution with the same shape --
 * minus everything that changes the answer: no roster editing, no pins, no re-optimize.
 *
 * Everything here is rendered on the server as well as in the browser, which is the other half of
 * the point: it is the one page on the site where a crawler can read what a result looks like.
 */

import Link from "next/link";
import { useMemo, useState } from "react";

import { LegSwitch } from "@/components/results/LegSwitch";
import { ResultSummary } from "@/components/results/ResultSummary";
import { RouteCard } from "@/components/results/RouteCard";
import { RouteMap, type MappedRoute } from "@/components/results/RouteMap";
import { useHoverHighlight } from "@/components/results/useHoverHighlight";
import { AppShell, RailSection } from "@/components/shell/AppShell";
import { ThemeToggle } from "@/components/shell/ThemeToggle";
import { Detail } from "@/components/ui/controls";
import { legOf, stopNumber, type LegChoice, type Route } from "@/lib/api/solutions";
import { demoEvent as event, demoHeadcount } from "@/lib/demo/event";
import { directionsUrl, legWaypoints } from "@/lib/results/googleMaps";
import { formatTimeInZone } from "@/lib/time";

const people = new Map(event.people.map((p) => [p.id, p]));

function at(participantId: string) {
  const person = people.get(participantId);
  return person ? { lat: person.lat, lng: person.lng } : null;
}

export function DemoDashboard() {
  const [leg, setLeg] = useState<LegChoice>("outbound");
  const [highlightedRouteId, setHighlightedRouteId] = useHoverHighlight();
  const routes = event.solution.routes;

  const mapped: MappedRoute[] = useMemo(
    () =>
      routes.map((route) => ({
        routeId: route.id,
        driverName: route.driver_name,
        home: at(route.driver_participant_id),
        stops: legOf(route, leg).stops.flatMap((stop) => {
          const point = at(stop.participant_id);
          return point ? [{ number: stopNumber(stop), label: stop.display_name, ...point }] : [];
        }),
      })),
    [routes, leg],
  );

  // Every coordinate is in the file, so unlike a live roster there is no missing stop to guard
  // against; the link opens real turn-by-turn directions between the made-up homes.
  function directionsFor(route: Route): string | null {
    const driverHome = at(route.driver_participant_id);
    const stops = legOf(route, leg).stops.flatMap((stop) => at(stop.participant_id) ?? []);
    if (!driverHome) return null;
    return directionsUrl(legWaypoints({ leg, driverHome, venue: event.venue, stops }));
  }

  const rail = (
    <>
      <div className="flex flex-col gap-3 px-5 pb-5 pt-6">
        <div className="flex items-center justify-between gap-3">
          <Link href="/" className="text-sm text-accent underline underline-offset-2">
            ← whodriveswho
          </Link>
          <ThemeToggle />
        </div>

        <h1 className="font-display text-2xl text-ink">{event.name}</h1>
        <p className="border-l-2 border-accent pl-3 text-[15px] leading-relaxed text-ink">
          An example with made-up people. {demoHeadcount()}, all going to the same practice — and
          this is the plan the app worked out for them.
        </p>
        <dl className="flex flex-col gap-3 border-t border-line pt-4">
          <Detail label="Destination">{event.venue.address}</Detail>
          <Detail label="Everyone arrives by">
            {formatTimeInZone(new Date(event.arrival_at), event.time_zone)}
          </Detail>
          <Detail label="Practice ends">
            {formatTimeInZone(new Date(event.ends_at), event.time_zone)}
          </Detail>
        </dl>
      </div>

      <RailSection title="Who drives who">
        <div>
          <LegSwitch leg={leg} onLeg={setLeg} />
        </div>
        <ResultSummary routes={routes} unassigned={event.solution.unassigned} />
        <div className="flex flex-col">
          {routes.map((route, index) => (
            <RouteCard
              key={route.id}
              route={route}
              index={index}
              leg={leg}
              timeZone={event.time_zone}
              directionsHref={directionsFor(route)}
              highlighted={highlightedRouteId === route.id}
              onHighlight={setHighlightedRouteId}
            />
          ))}
        </div>
      </RailSection>

      <RailSection title="How it was worked out">
        <p className="text-[15px] leading-relaxed text-ink">
          Each car picks up the riders who are on its way, in the order that keeps everyone&apos;s
          time in the car short, and gets them there by the time practice starts. The way back is
          planned on its own, so drop-offs need not mirror the pickups.
        </p>
        <p className="text-[15px] leading-relaxed text-ink-muted">
          Lines on the map join the stops directly. For real directions, each car has a Google Maps
          link.
        </p>
        <Link
          href="/"
          className="self-start rounded-[2px] bg-accent px-4 py-2 text-sm font-medium text-accent-ink transition-colors hover:bg-accent-hover"
        >
          Plan your own →
        </Link>
      </RailSection>
    </>
  );

  const canvas = (
    <RouteMap
      routes={mapped}
      venue={event.venue}
      leg={leg}
      highlightedRouteId={highlightedRouteId}
    />
  );

  return <AppShell rail={rail} canvas={canvas} />;
}
