/**
 * Geocoding calls.
 *
 * Both go through our API rather than the provider, which is what keeps the ORS key off the page
 * (docs/design.md 4.4). A 503 here means the geocoder is unavailable, and the correct response is
 * to let the coordinator place the pin by hand rather than to block them -- coordinates may always
 * be supplied directly.
 */

import { api, unwrap } from "./client";
import type { components } from "./schema";

export type Place = components["schemas"]["PlaceRead"];
export type Resolution = components["schemas"]["ResolutionRead"];

/** Shortest query the API will accept; below this it answers 422 without calling the provider. */
export const MIN_QUERY = 3;

export async function suggest(q: string): Promise<Place[]> {
  if (q.trim().length < MIN_QUERY) return [];
  const body = unwrap(await api.GET("/v1/geocode/autocomplete", { params: { query: { q } } }));
  return body.suggestions;
}

/** Resolve complete addresses. One result per input, in order, `place: null` where nothing matched. */
export async function resolve(addresses: string[]): Promise<Resolution[]> {
  if (addresses.length === 0) return [];
  const body = unwrap(await api.POST("/v1/geocode", { body: { addresses } }));
  return body.results;
}
