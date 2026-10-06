"use client";

import Link from "next/link";
import { useState, useSyncExternalStore } from "react";

import { CreateEventForm } from "@/components/CreateEventForm";
import { DestinationMap, type Point } from "@/components/DestinationMap";
import { AppShell, RailSection } from "@/components/shell/AppShell";
import { Button } from "@/components/ui/controls";
import {
  forgetToken,
  knownEventsServerSnapshot,
  knownEventsSnapshot,
  subscribeToKnownEvents,
} from "@/lib/api/tokens";

export default function Home() {
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
        <h1 className="font-display text-2xl text-ink">whodriveswho</h1>
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
          <ul className="-mx-2 divide-y divide-line border-y border-line">
            {known.map((publicId) => (
              <li key={publicId} className="group flex items-center gap-2 px-2">
                <Link
                  href={`/events/${publicId}`}
                  className="flex-1 truncate py-2.5 font-mono text-sm text-accent transition-colors"
                >
                  {publicId}
                </Link>
                <Button
                  variant="ghost"
                  type="button"
                  onClick={() => forgetToken(publicId)}
                  aria-label={`Remove ${publicId} from this device`}
                  title="Remove from this device"
                >
                  Remove
                </Button>
              </li>
            ))}
          </ul>
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
