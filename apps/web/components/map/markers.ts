/**
 * One set of map symbols, shared by every map in the app.
 *
 * These lived as three private helpers in three components, and they had drifted into three
 * different answers to the same question. The destination in particular was drawn as a red circle
 * on the roster map, a red rounded square on the results map, and MapLibre's default blue teardrop
 * on the create screen -- where `#1d4ed8` is also the first car's colour, so the venue read as
 * somebody's car. Both of the rules that broke are written down in this codebase: `routeColor`
 * excludes the destination's red "so the venue never reads as somebody's car", and the venue is a
 * square so it is "distinguishable without relying on colour alone". A symbol vocabulary only works
 * if it is the same vocabulary everywhere, which means it has to live in one file.
 *
 * The grammar:
 *
 *  - **Square** is the destination. One per map, never a person.
 *  - **Filled circle** is a person at a place -- a pickup on the roster, a numbered stop on a route.
 *  - **Hollow circle** is a driver's own home, so it is not counted as a pickup.
 *
 * Shape carries the distinction and colour reinforces it, rather than colour carrying it alone.
 */

import { DESTINATION_COLOR } from "@/lib/results/colors";

/** White ring and a drop shadow: these sit on a pale basemap, and need an edge against it. */
const RING = "border:2px solid white;box-shadow:0 1px 3px rgba(0,0,0,.4)";

function element(css: string, label: string): HTMLDivElement {
  const el = document.createElement("div");
  el.style.cssText = css;
  // `title` rather than an `aria-label`: these are decorative duplicates of a list that is already
  // on screen and already readable, so they offer a hover hint without adding noise to the tree.
  el.title = label;
  return el;
}

/**
 * The destination. A rounded square, in the one red the car palette leaves free.
 *
 * `className` is carried so the roster map can keep its `carpool-pin` hook, which its hover
 * styling uses.
 */
export function venuePin(label: string, className?: string): HTMLDivElement {
  const el = element(
    `width:18px;height:18px;border-radius:4px;background:${DESTINATION_COLOR};${RING}`,
    label,
  );
  if (className) el.className = className;
  return el;
}

/** A person at a place: a pickup on the roster, or an unnumbered stop. */
export function personPin(color: string, label: string, className?: string): HTMLDivElement {
  const el = element(
    `width:18px;height:18px;border-radius:9999px;background:${color};${RING};` +
      "cursor:pointer;transition:transform 120ms",
    label,
  );
  if (className) el.className = className;
  return el;
}

/** A numbered stop on a route. Larger than a plain pickup, because it carries a digit. */
export function stopPin(color: string, label: string, number: number): HTMLDivElement {
  const el = element(
    `display:flex;align-items:center;justify-content:center;width:22px;height:22px;` +
      `border-radius:9999px;background:${color};${RING};` +
      "color:white;font:600 11px/1 ui-sans-serif,system-ui,sans-serif",
    label,
  );
  el.textContent = String(number);
  return el;
}

/** A driver's own home: their car's colour, hollow, so it is not mistaken for a pickup. */
export function homePin(color: string, label: string): HTMLDivElement {
  return element(
    `width:16px;height:16px;border-radius:9999px;background:white;` +
      `border:3px solid ${color};box-shadow:0 1px 3px rgba(0,0,0,.4)`,
    label,
  );
}
