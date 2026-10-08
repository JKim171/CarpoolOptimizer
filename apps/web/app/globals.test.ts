/**
 * The dark palette is declared twice. This is what keeps the two copies identical.
 *
 * `globals.css` has to reach the dark tokens two ways -- from `prefers-color-scheme` when no theme
 * has been chosen, and from `data-theme="dark"` when one has -- and CSS has no way to share one
 * declaration block between a media query and a plain selector. So the values are duplicated, and
 * a duplicated palette drifts: someone adjusts a contrast problem in the block they happened to
 * open, ships it, and the app is now two slightly different dark themes depending on whether the
 * reader ever touched the control. That is a bug nobody would find by looking at one screen.
 *
 * Same guard the DB models get from the migration drift test and the API contract gets from
 * `test_openapi_contract.py`: the invariant is checked by the build rather than by a comment.
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

// Comments go first. This file is heavily commented and those comments name the very selectors
// being searched for, so scanning the raw text would sooner or later anchor on prose.
const css = readFileSync(join(__dirname, "globals.css"), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");

/**
 * Pull the declarations out of a `{ ... }` block, given something that identifies its opening.
 *
 * Deliberately a brace-counting scan rather than a regex: the follows-the-OS copy is nested inside
 * an `@media` block, so the first `}` after the selector is the end of the inner block in one case
 * and `/.../` would have to know which. Counting is the thing that cannot be fooled.
 */
function declarationsAfter(marker: string): Record<string, string> {
  const start = css.indexOf(marker);
  expect(start, `marker not found in globals.css: ${marker}`).toBeGreaterThan(-1);

  // The marker is a selector, never including its brace: searching from `start` rather than from
  // the end of the marker is what makes that true for the bare `:root` case too.
  const open = css.indexOf("{", start);
  expect(open, `no block opens after: ${marker}`).toBeGreaterThan(-1);

  let depth = 0;
  let end = -1;
  for (let i = open; i < css.length; i += 1) {
    if (css[i] === "{") depth += 1;
    else if (css[i] === "}") {
      depth -= 1;
      if (depth === 0) {
        end = i;
        break;
      }
    }
  }
  expect(end, `unbalanced braces after: ${marker}`).toBeGreaterThan(-1);

  const body = css.slice(open + 1, end);
  const declarations: Record<string, string> = {};
  for (const [, property, value] of body.matchAll(/([\w-]+)\s*:\s*([^;}]+)[;}]?/g)) {
    declarations[property] = value.trim();
  }
  return declarations;
}

describe("the dark palette", () => {
  const followsTheOs = declarationsAfter(':root:not([data-theme="light"])');
  const chosen = declarationsAfter(':root[data-theme="dark"]');

  it("declares the same tokens whether it was chosen or inherited from the OS", () => {
    expect(chosen).toEqual(followsTheOs);
  });

  it("is not vacuously equal -- both blocks were actually found and parsed", () => {
    // A bad selector marker would make `declarationsAfter` throw, but a *renamed* token everywhere
    // would leave two empty objects comparing equal. Anchor on the ones the layout cannot lose.
    for (const block of [followsTheOs, chosen]) {
      expect(Object.keys(block).length).toBeGreaterThan(10);
      expect(block).toHaveProperty("--surface");
      expect(block).toHaveProperty("--ink");
      // Native widgets -- the date input, the `<select>` popups, the rail's scrollbar -- are
      // painted by the browser from this, not from the tokens above it.
      expect(block["color-scheme"]).toBe("dark");
    }
  });

  it("leaves the light palette as the default, with no attribute needed", () => {
    const base = declarationsAfter("\n:root");
    expect(base["color-scheme"]).toBe("light");
    expect(base["--surface"]).not.toBe(chosen["--surface"]);
  });
});
