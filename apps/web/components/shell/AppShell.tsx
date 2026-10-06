"use client";

/**
 * The app frame: a rail you work in, and a map that fills everything else.
 *
 * **Why this replaced a scrolling document.** Every screen here used to be a column of sections --
 * header, map, roster table, forms, results -- that you scrolled through, with the map appearing
 * twice as two separate plates. The typography of that document was worked over carefully, but the
 * shape was wrong for what the product does: deciding who drives who is a spatial question, and a
 * map that is a figure between two form fields is being asked to illustrate rather than to answer.
 * Making the results map full-bleed fixed exactly one screen and made the other two disagree with
 * it. The map is now the canvas and the panels are the margin.
 *
 * **What this buys beyond looking right.** The roster map was deliberately *not* full-bleed before,
 * because hovering a table row highlights its pin and that pairing only works while both are on
 * screen. In a shell both are always on screen, so the constraint that kept the map small is gone.
 * The same is true of the results list: a car's colour in the rail and its line on the map no
 * longer scroll away from each other.
 *
 * **There is no page scroll.** The shell owns the viewport and the rail scrolls inside itself. That
 * is what retired `Bleed` and the `overflow-x-clip` on `<body>`, both of which existed only so a
 * map could escape a text measure; a canvas has no measure to escape.
 */

import { useState, type ReactNode } from "react";

/**
 * The rail is first in the DOM and the map second, so tabbing reaches the controls before the
 * canvas and a screen reader meets the page's actual content first. On desktop the grid places
 * them in that same order anyway; on a phone both are positioned, so DOM order costs nothing.
 */
export function AppShell({ rail, canvas }: { rail: ReactNode; canvas: ReactNode }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="relative h-dvh overflow-hidden lg:grid lg:grid-cols-[23rem_1fr] xl:grid-cols-[27rem_1fr]">
      {/*
        On a phone this is a bottom sheet over a full-screen map, which is the shape that survives
        the width: a 23rem rail beside a map is two unusable columns at 390px. The sheet peeks at
        just under half the viewport and opens to most of it, so the map is never fully covered and
        the thing you are reading is never a sliver.
      */}
      <aside
        className={
          "absolute inset-x-0 bottom-0 z-20 flex flex-col rounded-t-2xl border-t border-line " +
          "bg-surface shadow-[0_-8px_24px_rgba(0,0,0,0.18)] transition-[height] duration-200 " +
          (expanded ? "h-[88dvh] " : "h-[46dvh] ") +
          "lg:static lg:z-auto lg:h-dvh lg:rounded-none lg:border-r lg:border-t-0 lg:shadow-none"
        }
      >
        <button
          type="button"
          onClick={() => setExpanded((open) => !open)}
          aria-expanded={expanded}
          className="group shrink-0 cursor-pointer py-3 lg:hidden"
        >
          <span className="sr-only">{expanded ? "Collapse the panel" : "Expand the panel"}</span>
          {/* A grab handle. Nothing drags yet -- it is a target and an affordance, and a tap is the
              reliable gesture; a drag that only sometimes catches is worse than a button. */}
          <span className="mx-auto block h-1 w-10 rounded-full bg-line-strong transition-colors group-hover:bg-ink-muted" />
        </button>

        {/* `min-h-0` is load-bearing: a flex child defaults to `min-height: auto`, which refuses to
            shrink below its content, and the rail would push its own scrollbar off the sheet. */}
        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain">{rail}</div>
      </aside>

      <div className="absolute inset-0 z-0 lg:static lg:h-dvh">{canvas}</div>
    </div>
  );
}

/**
 * A titled block inside the rail.
 *
 * The rail is a narrow column of unrelated things -- events, a roster, an answer -- so each needs a
 * boundary. A rule above the heading does it the way the document version did, which is one line
 * rather than a border around everything; see the conventions in `components/ui/controls.tsx`.
 * `first:border-t-0` because the top of the rail is already an edge.
 */
export function RailSection({
  title,
  meta,
  actions,
  children,
}: {
  title: string;
  meta?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="flex flex-col gap-4 border-t border-line px-5 py-6 first:border-t-0">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <h2 className="font-display text-lg text-ink">{title}</h2>
        {(meta || actions) && (
          <div className="flex items-center gap-3">
            {meta && <span className="text-xs text-ink-muted">{meta}</span>}
            {actions}
          </div>
        )}
      </div>
      {children}
    </section>
  );
}
