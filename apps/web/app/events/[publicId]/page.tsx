"use client";

/**
 * The organizer's view of one event. The roster table lands in the next slice and the results view
 * after it; this is the shell they hang off, and it is already the page an organizer returns to.
 */

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { use } from "react";

import { Detail, Page, Panel, Problem } from "@/components/ui/controls";
import { ApiError } from "@/lib/api/client";
import { eventKeys, fetchEvent } from "@/lib/api/events";
import { formatInZone } from "@/lib/time";

export default function EventPage({ params }: PageProps<"/events/[publicId]">) {
  const { publicId } = use(params);
  const event = useQuery({
    queryKey: eventKeys.detail(publicId),
    queryFn: () => fetchEvent(publicId),
  });

  return (
    <Page>
      <div>
        <Link href="/" className="text-sm text-accent hover:underline">
          ← All events
        </Link>
        <p className="mt-2 font-mono text-xs text-ink-muted">{publicId}</p>
      </div>

      {event.isPending && <p className="text-sm text-ink-muted">Loading…</p>}

      {event.isError && (
        // The API answers an unknown event, a revoked token and another event's token all with 401,
        // deliberately, so that the status cannot be used to discover which handles are real
        // (docs/design.md 6.1). The UI cannot tell them apart either, and must not pretend to.
        <Problem>
          {event.error instanceof ApiError
            ? event.error.message
            : "Could not load this event. Check your connection and try again."}
        </Problem>
      )}

      {event.isSuccess && (
        <>
          <h1 className="text-2xl font-semibold text-ink">{event.data.name}</h1>
          <dl className="grid gap-4 sm:grid-cols-2">
            <Detail label="Destination">{event.data.destination.address}</Detail>
            <Detail label="Status">{event.data.status}</Detail>
            <Detail label="Everyone arrives by">
              {formatInZone(new Date(event.data.arrival_at), event.data.timezone)}
            </Detail>
            <Detail label="Event ends">
              {formatInZone(new Date(event.data.ends_at), event.data.timezone)}
            </Detail>
            <Detail label="Time zone">{event.data.timezone}</Detail>
            <Detail label="Roster version">{event.data.participants_version}</Detail>
          </dl>

          <Panel className="text-sm text-ink-muted">
            The roster table and the results view arrive in the next two slices. Until then this
            event exists and can be optimized through the API.
          </Panel>
        </>
      )}
    </Page>
  );
}
