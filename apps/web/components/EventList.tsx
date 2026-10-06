"use client";

/**
 * The events this browser holds a token for, named rather than numbered.
 *
 * This list was bare `public_id`s -- six rows of `tfr5zmnypv`, `mcngd7ej8n`, indistinguishable --
 * because the name is not in localStorage; only the token is. Showing one therefore costs a request
 * per event, which is why it was scoped out while the list lived at the bottom of a home page. In
 * the shell it is the rail's navigation, so it has to say what each event *is*.
 *
 * The requests go through the same query key the event page uses, so opening one of these is served
 * from cache rather than refetched.
 *
 * **A row that will not load keeps its handle and says nothing else.** The API answers an unknown
 * event, a revoked token and another event's token all with 401, deliberately, so that the status
 * cannot be used to discover which handles are real (docs/design.md 6.1). This component cannot
 * tell those apart either and must not imply it can -- so a failed row is not labelled "deleted" or
 * "expired", it simply stays a handle, and the organizer can still open it to see the same
 * ambiguous message or forget it.
 */

import Link from "next/link";
import { useQueries } from "@tanstack/react-query";

import { Button } from "@/components/ui/controls";
import { eventKeys, fetchEvent, type Event } from "@/lib/api/events";
import { forgetToken } from "@/lib/api/tokens";
import { formatInZone } from "@/lib/time";

export function EventList({ publicIds }: { publicIds: string[] }) {
  const results = useQueries({
    queries: publicIds.map((publicId) => ({
      queryKey: eventKeys.detail(publicId),
      queryFn: () => fetchEvent(publicId),
      // One attempt. A 401 here is an answer, not a blip, and retrying it three times per row
      // turns opening the rail into a burst of requests that cannot succeed.
      retry: false,
      staleTime: 60_000,
    })),
  });

  const rows = publicIds.map((publicId, index) => ({
    publicId,
    event: results[index]?.data as Event | undefined,
    pending: results[index]?.isPending ?? false,
  }));

  /**
   * Soonest-dated first, and anything without a date last.
   *
   * localStorage enumerates keys in an order nobody chose, which is as arbitrary as the handles
   * were. A row that has not loaded yet sorts to the bottom rather than jumping once it resolves.
   */
  const sorted = [...rows].sort((a, b) => {
    if (!a.event) return b.event ? 1 : 0;
    if (!b.event) return -1;
    return Date.parse(b.event.arrival_at) - Date.parse(a.event.arrival_at);
  });

  return (
    <ul className="-mx-2 divide-y divide-line border-y border-line">
      {sorted.map(({ publicId, event, pending }) => (
        <li key={publicId} className="group flex items-center gap-1 px-2">
          <Link href={`/events/${publicId}`} className="min-w-0 flex-1 py-2.5">
            <span
              className={`block truncate text-[15px] text-accent ${event ? "" : "font-mono text-sm"}`}
            >
              {event ? event.name : publicId}
            </span>
            {/*
              Only when there is something to say. A row that did not load has nothing but its
              handle, and that is already on the line above -- printing it twice looks like a
              defect rather than like the absence of information it actually is.
            */}
            {(event || pending) && (
              <span className="block truncate text-xs text-ink-muted">
                {event ? (
                  <>
                    {formatInZone(new Date(event.arrival_at), event.timezone)}
                    {" · "}
                    <span className="font-mono">{publicId}</span>
                  </>
                ) : (
                  "Loading…"
                )}
              </span>
            )}
          </Link>
          <Button
            variant="ghost"
            type="button"
            onClick={() => forgetToken(publicId)}
            aria-label={`Remove ${event ? event.name : publicId} from this device`}
            title="Remove from this device"
          >
            Remove
          </Button>
        </li>
      ))}
    </ul>
  );
}
