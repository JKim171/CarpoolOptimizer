"use client";

import Link from "next/link";
import { useSyncExternalStore } from "react";

import { CreateEventForm } from "@/components/CreateEventForm";
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
    <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col gap-8 p-6 sm:p-8">
      <header>
        <h1 className="text-2xl font-semibold">CarpoolOptimizer</h1>
        <p className="mt-1 text-sm opacity-70">
          Enter a roster, get an assignment: who drives whom, in what pickup order, out and back.
        </p>
      </header>

      {known.length > 0 && (
        <section>
          <h2 className="text-sm font-medium">Your events on this device</h2>
          <ul className="mt-2 flex flex-col gap-1">
            {known.map((publicId) => (
              <li key={publicId}>
                <Link
                  href={`/events/${publicId}`}
                  className="text-sm text-blue-700 underline underline-offset-2 dark:text-blue-400"
                >
                  {publicId}
                </Link>
              </li>
            ))}
          </ul>
          <p className="mt-2 text-xs opacity-60">
            Organizer tokens are kept in this browser only. On another device you will need the link
            and its token.
          </p>
        </section>
      )}

      <section>
        <h2 className="mb-3 text-sm font-medium">New event</h2>
        <CreateEventForm />
      </section>
    </main>
  );
}
