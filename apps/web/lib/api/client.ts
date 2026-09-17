/**
 * The typed API client.
 *
 * Paths, request bodies and responses are all typed from `schema.d.ts`, which is generated from the
 * API's own OpenAPI document (see `carpool_api/contract.py`). Nothing here restates the shape of a
 * payload: if a field is renamed in a Pydantic model, this file stops compiling, which is the whole
 * point of generating rather than hand-writing the types.
 */

import createClient from "openapi-fetch";

import type { components, paths } from "./schema";
import { readToken } from "./tokens";

/**
 * Baked in at build time by Next. There is no sensible default: pointing a misconfigured deploy at
 * localhost would fail in a way that looks like the API being down, so an absent value is loud.
 */
const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL;
if (!baseUrl) {
  throw new Error(
    "NEXT_PUBLIC_API_BASE_URL is not set. Copy apps/web/.env.example to .env.local for development.",
  );
}

export const api = createClient<paths>({ baseUrl });

/** Header block for a request authenticated as the organizer of `publicId`. */
export function organizerAuth(publicId: string): Record<string, string> {
  const token = readToken(publicId);
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/**
 * A failed request, carrying the status so callers can branch on it.
 *
 * 401 is the interesting one: the API answers an unknown event, a revoked token and another
 * event's token all with 401, deliberately, so that an unauthenticated caller cannot use the
 * status to discover which event handles are real (docs/design.md 6.1). The UI therefore cannot
 * distinguish "wrong token" from "no such event" either, and must not pretend to.
 */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

type ValidationError = components["schemas"]["HTTPValidationError"];

/** Turn an error body into something worth showing a coordinator mid-event. */
export function describeError(status: number, body: unknown): ApiError {
  if (status === 401) {
    return new ApiError(
      status,
      "That organizer link is not valid for this event, or the event does not exist.",
    );
  }
  const detail = (body as ValidationError | { detail?: string } | undefined)?.detail;
  if (typeof detail === "string") return new ApiError(status, detail);
  if (Array.isArray(detail) && detail.length > 0) {
    // FastAPI reports the offending field as a `loc` path; the last element is the field name.
    const first = detail[0];
    const field = first.loc?.[first.loc.length - 1];
    return new ApiError(status, field ? `${String(field)}: ${first.msg}` : first.msg);
  }
  return new ApiError(status, `Request failed (${status}).`);
}

/** Narrow an openapi-fetch result to its data, throwing a described error otherwise. */
export function unwrap<T>(result: { data?: T; error?: unknown; response: Response }): T {
  if (result.error !== undefined || result.data === undefined) {
    throw describeError(result.response.status, result.error);
  }
  return result.data;
}
