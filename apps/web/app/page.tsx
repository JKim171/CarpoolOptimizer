"use client";

import Link from "next/link";
import { useSyncExternalStore } from "react";

import { CreateEventForm } from "@/components/CreateEventForm";
import { Page, Panel } from "@/components/ui/controls";
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

  return (
    <Page>
      <header>
        <h1 className="text-2xl font-semibold text-ink">CarpoolOptimizer</h1>
        <p className="mt-1 text-sm text-ink-muted">
          Enter a roster, get an assignment: who drives whom, in what pickup order, out and back.
        </p>
      </header>

      {/*
       * This list is whatever tokens localStorage holds, so it keeps listing an event that has
       * since been deleted or archived, or whose token expired -- opening one gets the 401 the
       * event page renders. A liveness check on mount was the alternative and is the wrong shape:
       * the 401 is deliberately ambiguous (docs/design.md 6.1), so it cannot distinguish "deleted"
       * from "expired token" and would have to report both as one vague message anyway. Letting
       * the organizer remove a dead row says exactly as much as the app actually knows.
       */}
      {known.length > 0 && (
        <section>
          <h2 className="mb-2 text-sm font-medium text-ink">Your events on this device</h2>
          <Panel className="p-0">
            <ul className="divide-y divide-line">
              {known.map((publicId) => (
                <li key={publicId} className="flex items-center gap-2 pr-2">
                  <Link
                    href={`/events/${publicId}`}
                    className="flex-1 px-4 py-3 font-mono text-sm text-accent hover:bg-surface-sunken"
                  >
                    {publicId}
                  </Link>
                  <button
                    type="button"
                    onClick={() => forgetToken(publicId)}
                    aria-label={`Remove ${publicId} from this device`}
                    title="Remove from this device"
                    className="rounded-md px-2 py-1 text-xs text-ink-muted hover:text-danger-ink"
                  >
                    Remove
                  </button>
                </li>
              ))}
            </ul>
          </Panel>
          <p className="mt-2 text-xs text-ink-muted">
            Organizer tokens are kept in this browser only. On another device you will need the link
            and its token. Removing forgets the token here — it does not delete the event.
          </p>
        </section>
      )}

      <section>
        <h2 className="mb-3 text-sm font-medium text-ink">New event</h2>
        <CreateEventForm />
      </section>
    </Page>
  );
}
