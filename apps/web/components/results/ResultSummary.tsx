/**
 * The answer in one line, before the evidence for it.
 *
 * Reading four route cards and adding them up is how you learned "four cars, eight riders, nobody
 * stranded" before this existed, and that is the one sentence an organizer actually wants -- the
 * cards are what you read *after* deciding the shape is acceptable.
 *
 * Counted here from the routes rather than read from `SolutionRead.metrics`, which is an untyped
 * object on the wire: a shape the schema does not describe is one the contract test cannot catch
 * drifting. Everything below is derived from fields `RouteRead` declares.
 *
 * "No ride" is always shown, including when it is zero. A count that appears only when it is bad
 * is a count you cannot trust the absence of, and "nobody was left out" is the single most
 * reassuring thing this screen can say (`UnassignedList` explains the same number at length).
 */

import { formatDuration, type Route, type Unassigned } from "@/lib/api/solutions";

function Stat({
  value,
  label,
  tone = "plain",
}: {
  value: string;
  label: string;
  tone?: "plain" | "warn";
}) {
  // `dt` before `dd` is the order the markup requires; `flex-col-reverse` puts the figure on top,
  // which is the order it is read in.
  return (
    <div className="flex flex-col-reverse">
      <dt className="mt-0.5 text-sm text-ink-muted">{label}</dt>
      <dd
        className={`whitespace-nowrap font-display text-2xl tabular-nums ${
          tone === "warn" ? "text-warn-ink" : "text-ink"
        }`}
      >
        {value}
      </dd>
    </div>
  );
}

export function ResultSummary({
  routes,
  unassigned,
}: {
  routes: Route[];
  unassigned: Unassigned[];
}) {
  const riders = routes.reduce((n, route) => n + route.seats_used, 0);
  const detour = routes.reduce((n, route) => n + route.detour_seconds, 0);
  const driving = routes.reduce((n, route) => n + route.total_duration_s, 0);

  return (
    // Rules above and below rather than a box: the figures are the loudest thing in the rail
    // already, and a border around them is one more rectangle for no information.
    //
    // **Two columns, always.** This was `grid-cols-2 sm:grid-cols-4`, which is the right instinct
    // and the wrong mechanism now that the panel lives in a rail: Tailwind's breakpoints measure
    // the *viewport*, and the viewport being wide is exactly when the rail is at its narrowest
    // relative to it. Four columns in a 23rem rail is about 98px each, which wrapped "1 h 46 min"
    // onto three lines. The rail's width is set by the shell rather than by the window, so the
    // count is too.
    <dl className="grid grid-cols-2 gap-x-4 gap-y-4 border-y border-line py-4">
      <Stat value={String(routes.length)} label={routes.length === 1 ? "car" : "cars"} />
      <Stat value={String(riders)} label={riders === 1 ? "rider" : "riders"} />
      <Stat
        value={String(unassigned.length)}
        label="no ride"
        tone={unassigned.length > 0 ? "warn" : "plain"}
      />
      {/* Detour, not total driving time: total is mostly the trip everyone was making anyway, so it
          barely moves between solutions. Detour is the part the solver is actually trading against
          a car, and the number that changes when you re-optimize. */}
      <Stat value={formatDuration(detour)} label="detour in all" />
      {/* On screen the four above are the decision; the total is here for anyone reading the page
          linearly, where "how much driving is this in all" is the obvious next question. */}
      <div className="sr-only">
        <dt>Driving in total, every car, this leg</dt>
        <dd>{formatDuration(driving)}</dd>
      </div>
    </dl>
  );
}
