"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";

import { ApiError } from "@/lib/api/client";

/**
 * One QueryClient per browser session, created in state rather than at module scope so that a
 * server render cannot share a cache between two users' requests.
 */
export function Providers({ children }: { children: React.ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            // A 401 means the stored organizer token is wrong for this event and will stay wrong;
            // retrying it three times just delays telling the coordinator that.
            retry: (failureCount, error) =>
              !(error instanceof ApiError && error.status === 401) && failureCount < 2,
            staleTime: 10_000,
          },
        },
      }),
  );
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
