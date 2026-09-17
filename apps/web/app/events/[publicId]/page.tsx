"use client";

/**
 * The organizer's view of one event. The roster table lands in the next slice and the results view
 * after it; this is the shell they hang off, and it is already the page an organizer returns to.
 */

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { use } from "react";

import { ApiError } from "@/lib/api/client";
import { eventKeys, fetchEvent } from "@/lib/api/events";
import { formatInZone } from "@/lib/time";

export default function EventPage({ params }: PageProps<"/events/[publicId]">) {
  const { publicId } = use(params);
  const event = useQuery({
    queryKey: eventKeys.detail(publicId),
    queryFn: () => fetchEvent(publicId),
  });

  if (event.isPending) {
    return <Shell publicId={publicId}>Loading…</Shell>;
  }

  if (event.isError) {
    // The API answers an unknown event, a revoked token and another event's token all with 401,
    // deliberately, so that the status cannot be used to discover which handles are real
    // (docs/design.md 6.1). The UI cannot tell them apart either, and must not pretend to.
    const message =
      event.error instanceof ApiError
        ? event.error.message
        : "Could not load this event. Check your connection and try again.";
    return (
      <Shell publicId={publicId}>
        <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-800 dark:bg-red-950 dark:text-red-200">
          {message}
        </p>
      </Shell>
    );
  }

  const { name, destination, arrival_at, ends_at, timezone, status, participants_version } =
    event.data;

  return (
    <Shell publicId={publicId}>
      <h1 className="text-2xl font-semibold">{name}</h1>
      <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
        <Row label="Destination">{destination.address}</Row>
        <Row label="Status">{status}</Row>
        <Row label="Everyone arrives by">{formatInZone(new Date(arrival_at), timezone)}</Row>
        <Row label="Event ends">{formatInZone(new Date(ends_at), timezone)}</Row>
        <Row label="Time zone">{timezone}</Row>
        <Row label="Roster version">{participants_version}</Row>
      </dl>

      <section className="mt-8 rounded-md border border-dashed border-black/15 p-4 text-sm opacity-70 dark:border-white/20">
        The roster table and the results view arrive in the next two slices. Until then this event
        exists and can be optimized through the API.
      </section>
    </Shell>
  );
}

function Shell({ publicId, children }: { publicId: string; children: React.ReactNode }) {
  return (
    <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col gap-4 p-6 sm:p-8">
      <Link
        href="/"
        className="text-sm text-blue-700 underline underline-offset-2 dark:text-blue-400"
      >
        ← All events
      </Link>
      <p className="font-mono text-xs opacity-50">{publicId}</p>
      {children}
    </main>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wide opacity-50">{label}</dt>
      <dd className="mt-0.5">{children}</dd>
    </div>
  );
}
