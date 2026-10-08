"use client";

/**
 * The landing screen: pick a destination on the canvas, create an event from the rail.
 *
 * This is the whole of what used to be `app/page.tsx`. It moved out so that the route itself could
 * be a server component and export its own `metadata` -- a client component cannot -- which is what
 * lets `/` state a canonical URL. See `app/page.tsx`.
 */

import { useState, useSyncExternalStore } from "react";

import { CreateEventForm } from "@/components/CreateEventForm";
import { EventList } from "@/components/EventList";
import { DestinationMap, type Point } from "@/components/DestinationMap";
import { AppShell, RailSection } from "@/components/shell/AppShell";
import { ThemeToggle } from "@/components/shell/ThemeToggle";
import {
  knownEventsServerSnapshot,
  knownEventsSnapshot,
  subscribeToKnownEvents,
} from "@/lib/api/tokens";

export function HomeDashboard() {
  // localStorage is not available while rendering on the server, so the list comes through
  // `useSyncExternalStore`: an empty server snapshot, the real one on the client, and no state
  // update in an effect to bridge them.
  const known = useSyncExternalStore(
    subscribeToKnownEvents,
    knownEventsSnapshot,
    knownEventsServerSnapshot,
  );

  // The destination being picked, owned here because both halves of the screen read it: the form
  // in the rail submits it, the map on the canvas shows and corrects it.
  const [address, setAddress] = useState("");
  const [point, setPoint] = useState<Point | null>(null);

  const rail = (
    <>
      <div className="flex flex-col gap-2 px-5 pb-5 pt-6">
        {/* The theme control sits with the wordmark rather than in a settings screen, because this
            app has no settings screen and one preference does not earn one. `items-start` so the
            control aligns to the cap height of the title rather than floating in the middle. */}
        <div className="flex items-start justify-between gap-3">
          <h1 className="font-display text-2xl text-ink">whodriveswho</h1>
          <ThemeToggle />
        </div>
        <p className="text-[15px] leading-relaxed text-ink-muted">
          Enter a roster, get an assignment: who drives who, in what pickup order, out and back.
        </p>
      </div>

      {/*
       * This list is whatever tokens localStorage holds, so it keeps listing an event that has
       * since been deleted or archived, or whose token expired -- opening one gets the 401 the
       * event page renders. A liveness check on mount was the alternative and is the wrong shape:
       * the 401 is deliberately ambiguous (docs/design.md 6.1), so it cannot distinguish "deleted"
       * from "expired token" and would have to report both as one vague message anyway. Letting
       * the organizer remove a dead row says exactly as much as the app actually knows.
       */}
      {known.length > 0 && (
        <RailSection title="Your events">
          <EventList publicIds={known} />
          <p className="text-xs text-ink-muted">
            Organizer tokens are kept in this browser only. On another device you will need the link
            and its token. Removing forgets the token here — it does not delete the event.
          </p>
        </RailSection>
      )}

      <RailSection title="New event">
        <CreateEventForm
          address={address}
          onAddress={setAddress}
          point={point}
          onPoint={setPoint}
        />
      </RailSection>
    </>
  );

  return <AppShell rail={rail} canvas={<DestinationMap point={point} onMove={setPoint} />} />;
}
