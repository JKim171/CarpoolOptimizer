"use client";

/**
 * The frame every map in this app renders into: fill the space, caption on top.
 *
 * All three maps used to size themselves -- `h-96`, `h-[28rem]`, `h-[65vh]` -- because each sat in
 * a scrolling document and had to claim a height from it. In the shell they all fill the canvas
 * instead, so the height belongs to the layout and none of them names one.
 *
 * The caption moved onto the map for the same reason. Below the map it was a line of text taking a
 * slice off the bottom of the canvas, and on a full-width map it ran to a measure nobody reads. As
 * an overlay it sits in the corner the map is least likely to be using, opposite MapLibre's own
 * attribution control, and `pointer-events-none` keeps it from swallowing a drag that starts
 * underneath it.
 */

import type { ReactNode, RefObject } from "react";

export function MapFrame({
  container,
  label,
  caption,
  overlay,
}: {
  container: RefObject<HTMLDivElement | null>;
  /** What the map is, for anyone who cannot see it. The caption is advice; this is the name. */
  label: string;
  caption?: ReactNode;
  /** Controls that belong to the map rather than to the panel -- a mode switch, a legend. */
  overlay?: ReactNode;
}) {
  return (
    <div className="relative h-full w-full bg-surface-sunken">
      <div ref={container} className="h-full w-full" role="application" aria-label={label} />

      {overlay && <div className="absolute left-4 top-4 z-10 flex flex-col gap-2">{overlay}</div>}

      {/*
        Full-strength ink, not `--ink-muted`.

        This is `text-xs`, which this project holds to 7:1, and muted ink over the plate measured
        5.44:1 in light and 6.11:1 in dark -- past AA, short of the bar, and the same miss session 18
        found in `Badge`. The fix there was to darken rather than to narrow the claim, and it applies
        twice over here: a caption sitting on a *map* has a varying ground under a translucent
        plate, which is the worst case for faint small type. The quiet comes from the size and the
        corner it sits in, not from greying the text.
      */}
      {caption && (
        <p className="pointer-events-none absolute bottom-2 left-2 z-10 max-w-md rounded-[2px] bg-surface/90 px-2 py-1 text-xs text-ink">
          {caption}
        </p>
      )}
    </div>
  );
}
