/**
 * `isPrivatePath` decides whether an event URL reaches a search index or an analytics provider.
 *
 * Both of those are one-way doors -- an indexed URL has to be removed through Search Console, and a
 * page view sent to a third party cannot be recalled -- so the predicate is tested directly rather
 * than trusted to read correctly. The case that matters most is the near-miss: a sibling path that
 * merely starts with the same letters must not be swept up, because that failure is silent in both
 * directions (a public page missing from the sitemap, and missing from its own analytics).
 */

import { describe, expect, it } from "vitest";

import { isPrivatePath, PRIVATE_PATH_PREFIX, SITE_URL } from "./seo";

describe("isPrivatePath", () => {
  it("treats an event page and everything under it as private", () => {
    expect(isPrivatePath("/events")).toBe(true);
    expect(isPrivatePath("/events/")).toBe(true);
    expect(isPrivatePath("/events/8kq2mz")).toBe(true);
    expect(isPrivatePath("/events/8kq2mz/anything-added-later")).toBe(true);
  });

  it("leaves the public pages alone", () => {
    expect(isPrivatePath("/")).toBe(false);
    expect(isPrivatePath("/privacy")).toBe(false);
    expect(isPrivatePath("/demo")).toBe(false);
  });

  it("does not sweep up a sibling path that shares the prefix", () => {
    // The whole reason this is not `startsWith("/events")`. A future public page explaining what an
    // event is would otherwise be excluded from the sitemap and from analytics, with nothing to say
    // so.
    expect(isPrivatePath("/events-explained")).toBe(false);
    expect(isPrivatePath("/eventsomething")).toBe(false);
  });
});

describe("the canonical origin", () => {
  it("is an absolute https origin with no trailing slash", () => {
    // `metadataBase` resolves every relative canonical and Open Graph URL against this, and a
    // trailing slash here produces `//` in each of them.
    expect(SITE_URL).toMatch(/^https:\/\/[^/]+$/);
  });

  it("states the private prefix as a rooted path", () => {
    // `app/robots.ts` and the `X-Robots-Tag` rule in `next.config.ts` both build a path pattern by
    // concatenating onto this, which only works if it is rooted and unslashed.
    expect(PRIVATE_PATH_PREFIX).toMatch(/^\/[^/]+$/);
  });
});
