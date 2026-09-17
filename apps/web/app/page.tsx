"use client";

import Link from "next/link";
import { useSyncExternalStore } from "react";

import { CreateEventForm } from "@/components/CreateEventForm";
import { Page, Panel } from "@/components/ui/controls";
import {
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
       * Known limitation: this list is whatever tokens localStorage holds, so it keeps listing an
       * event that has since been deleted, archived, or whose token expired -- opening one of those
       * gets the 401 the event page renders. Resolving it needs either a liveness check on mount or
       * a "remove from this device" action, and it belongs with the roster slice rather than here.
       */}
      {known.length > 0 && (
        <section>
          <h2 className="mb-2 text-sm font-medium text-ink">Your events on this device</h2>
          <Panel className="p-0">
            <ul className="divide-y divide-line">
              {known.map((publicId) => (
                <li key={publicId}>
                  <Link
                    href={`/events/${publicId}`}
                    className="block px-4 py-3 font-mono text-sm text-accent hover:bg-surface-sunken"
                  >
                    {publicId}
                  </Link>
                </li>
              ))}
            </ul>
          </Panel>
          <p className="mt-2 text-xs text-ink-muted">
            Organizer tokens are kept in this browser only. On another device you will need the link
            and its token.
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
