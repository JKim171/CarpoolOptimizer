/**
 * `allowPageView` is the only thing standing between an event URL and a third-party analytics
 * provider, and a send cannot be undone. So it is tested the way the backup script's integrity check
 * is justified: the failure is silent, discovered late, and not recoverable at the moment you notice.
 */

import { describe, expect, it } from "vitest";

import { allowPageView } from "./analytics";

const at = (url: string) => ({ url });

describe("allowPageView", () => {
  it("sends views of the public pages", () => {
    expect(allowPageView(at("https://www.whodriveswho.com/"))).toEqual(
      at("https://www.whodriveswho.com/"),
    );
  });

  it("keeps the campaign parameters on a public URL", () => {
    // These are the point of measuring at all -- which post sent someone here. They describe the
    // link, not the person, and the page they land on holds nothing private.
    const landing = at("https://www.whodriveswho.com/?utm_source=reddit&utm_campaign=scouting");
    expect(allowPageView(landing)).toEqual(landing);
  });

  it("drops an event page entirely, id and all", () => {
    expect(allowPageView(at("https://www.whodriveswho.com/events/8kq2mz"))).toBeNull();
    expect(allowPageView(at("https://www.whodriveswho.com/events/8kq2mz?from=sms"))).toBeNull();
    expect(allowPageView(at("https://www.whodriveswho.com/events"))).toBeNull();
  });

  it("returns the event object itself, not a copy", () => {
    // The provider is handed back whatever this returns, so a reconstructed object would silently
    // drop any field the provider added and this module does not know about.
    const view = at("https://www.whodriveswho.com/");
    expect(allowPageView(view)).toBe(view);
  });

  it("fails closed on a URL it cannot parse", () => {
    // It cannot clear what it cannot read. One missing row in a count is the right price.
    expect(allowPageView(at("/events/8kq2mz"))).toBeNull();
    expect(allowPageView(at(""))).toBeNull();
    expect(allowPageView(at("not a url at all"))).toBeNull();
  });
});
