"use client";

/**
 * The hovered car, kept honest across a scroll.
 *
 * `onMouseEnter`/`onMouseLeave` pair up correctly only while the *pointer* is the thing that moves.
 * Scrolling with the pointer at rest moves the cards instead, and the browser owes no boundary
 * event for that: the card the cursor started on stays "entered" while a different card slides
 * underneath the cursor.
 *
 * A shaded row would be a cosmetic complaint. The id is read by `RouteMap` as well, which fades
 * every route that is not the highlighted one, so a stale id leaves the full-bleed map showing one
 * car solid and the rest at quarter opacity -- pointing confidently at a car nobody is pointing at.
 *
 * So the pointer position is tracked, and after a scroll the document is asked what is *actually*
 * under it. That re-points the highlight rather than merely dropping it: scroll a different car
 * under the cursor and the highlight follows it, which is what hovering is supposed to mean.
 */

import { useEffect, useRef, useState } from "react";

/** Set by `RouteCard` on its own element; the only thing this hook knows about a card. */
export const ROUTE_ID_ATTR = "data-route-id";

export function useHoverHighlight() {
  const [highlightedRouteId, setHighlightedRouteId] = useState<string | null>(null);
  // Null until the pointer has moved at least once, and again whenever it leaves the window: with
  // no position worth testing, a scroll can only clear. Without that second case, moving the mouse
  // off the page and scrolling by keyboard would highlight whatever slid under a cursor that is no
  // longer there.
  const pointer = useRef<{ x: number; y: number } | null>(null);

  useEffect(() => {
    const track = (event: PointerEvent) => {
      pointer.current = { x: event.clientX, y: event.clientY };
    };
    // `relatedTarget === null` is the pointer leaving the window, as opposed to crossing between
    // two elements inside it.
    const forget = (event: PointerEvent) => {
      if (event.relatedTarget === null) pointer.current = null;
    };

    // `elementFromPoint` reads layout, so it is held to one call per frame rather than one per
    // scroll event.
    let frame = 0;
    const resync = () => {
      if (frame) return;
      frame = requestAnimationFrame(() => {
        frame = 0;
        const at = pointer.current;
        const under = at ? document.elementFromPoint(at.x, at.y) : null;
        const card = under?.closest<HTMLElement>(`[${ROUTE_ID_ATTR}]`);
        setHighlightedRouteId(card?.dataset.routeId ?? null);
      });
    };

    window.addEventListener("pointermove", track, { passive: true });
    window.addEventListener("pointerout", forget, { passive: true });
    window.addEventListener("scroll", resync, { passive: true });
    return () => {
      window.removeEventListener("pointermove", track);
      window.removeEventListener("pointerout", forget);
      window.removeEventListener("scroll", resync);
      if (frame) cancelAnimationFrame(frame);
    };
  }, []);

  return [highlightedRouteId, setHighlightedRouteId] as const;
}
