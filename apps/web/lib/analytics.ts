/**
 * The filter that decides which page views are allowed to leave this origin.
 *
 * Analytics on this site has a hard limit that most sites do not: an event URL contains the event's
 * `public_id`, and the page behind it renders participants' names and home addresses for groups that
 * may include minors (CLAUDE.md, docs/design.md 2, 5.3.2). Sending that path to a third party would
 * hand out a list of real event handles, and it cannot be taken back afterwards. So event page views
 * are dropped outright rather than anonymised -- there is no version of that URL worth the risk, and
 * the numbers that would justify keeping it (how many events exist, how many were solved) come from
 * the database instead, where they are both free and more accurate.
 *
 * This is a plain function over a structural type rather than something importing the provider's
 * types, so it can be tested without loading the provider at all. `WebAnalytics` wires it up.
 */

import { isPrivatePath } from "./seo";

/** The shape this needs from a provider's event. Structural on purpose -- see above. */
export type PageView = { url: string };

/**
 * Returns the event to send, or `null` to drop it.
 *
 * Fails closed. A URL this cannot parse is dropped rather than forwarded: the whole job of this
 * function is to recognise the paths that must not be sent, and a value it cannot read is a value it
 * cannot clear. The cost of a wrong `null` is one missing row in a pageview count; the cost of a
 * wrong send is a permanent disclosure.
 */
export function allowPageView<E extends PageView>(event: E): E | null {
  let pathname: string;
  try {
    pathname = new URL(event.url).pathname;
  } catch {
    return null;
  }
  return isPrivatePath(pathname) ? null : event;
}
