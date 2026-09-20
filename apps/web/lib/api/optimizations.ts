/**
 * Optimization jobs.
 *
 * Written against the *async* contract -- enqueue, then poll until terminal -- even though the API
 * currently solves inline and hands back a finished job in the POST response. That is a deliberate
 * seam: `docs/design.md` 4.2 makes a separate worker a Week 4 decision, and a client that assumes
 * the answer arrives with the 202 is a client that breaks the day one lands. Polling a job that is
 * already `succeeded` costs exactly one request.
 */

import { api, describeError, organizerAuth, unwrap } from "./client";
import type { components } from "./schema";

export type Job = components["schemas"]["JobRead"];
export type JobStatus = Job["status"];
export type Weights = components["schemas"]["Weights"];

/** Statuses a job can still move out of. Anything else is final and stops the polling. */
const IN_FLIGHT: readonly JobStatus[] = ["queued", "running"];

export function isTerminal(status: JobStatus): boolean {
  return !IN_FLIGHT.includes(status);
}

/**
 * The outcome of asking for an optimization.
 *
 * `conflict` is not an error to show and forget: the API answers 409 when another job is already in
 * flight for this event, and hands back the id of the job that won so the client can poll *that*
 * one instead. Retrying would hit the same partial unique index and fail again.
 */
export type StartResult =
  | { kind: "job"; job: Job }
  | { kind: "conflict"; existingJobId: string | null; detail: string };

type JobConflict = components["schemas"]["JobConflict"];

/**
 * Ask for a solve.
 *
 * 202 means a job was created; 200 means an existing one is being returned -- an idempotent replay,
 * or a fingerprint that was already solved. The body is identical, so this does not distinguish
 * them; the caller polls `job_id` either way.
 */
export async function startOptimization(publicId: string): Promise<StartResult> {
  const result = await api.POST("/v1/events/{public_id}/optimizations", {
    params: { path: { public_id: publicId }, header: undefined },
    headers: organizerAuth(publicId),
    body: { algorithm: "greedy" },
  });

  if (result.response.status === 409) {
    const body = result.error as JobConflict | undefined;
    return {
      kind: "conflict",
      existingJobId: body?.existing_job_id ?? null,
      detail: body?.detail ?? "An optimization is already running for this event.",
    };
  }
  if (result.error !== undefined || result.data === undefined) {
    throw describeError(result.response.status, result.error);
  }
  return { kind: "job", job: result.data };
}

export async function fetchJob(publicId: string, jobId: string): Promise<Job> {
  return unwrap(
    await api.GET("/v1/events/{public_id}/optimizations/{job_id}", {
      params: { path: { public_id: publicId, job_id: jobId }, header: undefined },
      headers: organizerAuth(publicId),
    }),
  );
}

/** Cooperative cancel: the solver checks the flag, so a running job stops at its next look. */
export async function cancelJob(publicId: string, jobId: string): Promise<Job> {
  return unwrap(
    await api.DELETE("/v1/events/{public_id}/optimizations/{job_id}", {
      params: { path: { public_id: publicId, job_id: jobId }, header: undefined },
      headers: organizerAuth(publicId),
    }),
  );
}

export const jobKeys = {
  detail: (publicId: string, jobId: string) => ["job", publicId, jobId] as const,
};

/** What to tell the organizer while a job is in flight, or about how it ended. */
export function describeJob(job: Job): string {
  switch (job.status) {
    case "queued":
      return "Queued…";
    case "running":
      return "Solving…";
    case "succeeded":
      return "Done.";
    case "cancelled":
      return "Cancelled.";
    case "failed":
      return job.error ? `Failed: ${job.error}` : "The solve failed.";
    default:
      return job.status;
  }
}
