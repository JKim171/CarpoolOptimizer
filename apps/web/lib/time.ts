/**
 * Wall-clock time in a named zone, to and from the instants the API stores.
 *
 * A coordinator reasons in wall-clock time -- "practice at 4pm" -- while the API takes an aware
 * datetime and an IANA zone name (docs/design.md 6). Converting between them is the kind of code
 * that is wrong for six months without anyone noticing, because it is only wrong near a
 * daylight-saving boundary and only by an hour. An hour is exactly enough to miss a practice.
 *
 * `TZDate` does the arithmetic rather than a hand-rolled `Intl` offset trick: the trick is
 * short, looks right, and gets the two ambiguous hours a year wrong.
 */

import { TZDate } from "@date-fns/tz";

/** The zone this browser is in, as the sensible default for a new event. */
export function localTimeZone(): string {
  return Intl.DateTimeFormat().resolvedOptions().timeZone;
}

/**
 * `<input type="datetime-local">` gives "YYYY-MM-DDTHH:mm" with no zone at all. Read as the
 * wall-clock reading of a clock in `timeZone`, and returned as an instant.
 *
 * Returns null for an empty or unparseable field, so a half-filled form is a validation message
 * rather than an `Invalid Date` reaching the API as "null".
 */
export function wallClockToInstant(value: string, timeZone: string): Date | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(value);
  if (!match) return null;
  const [, year, month, day, hour, minute] = match.map(Number);

  const date = new TZDate(year, month - 1, day, hour, minute, 0, 0, timeZone);
  if (Number.isNaN(date.getTime())) return null;
  return new Date(date.getTime());
}

/** The inverse: an instant rendered as the wall clock would read it in `timeZone`. */
export function instantToWallClock(instant: Date, timeZone: string): string {
  const zoned = new TZDate(instant.getTime(), timeZone);
  const pad = (n: number) => String(n).padStart(2, "0");
  return (
    `${zoned.getFullYear()}-${pad(zoned.getMonth() + 1)}-${pad(zoned.getDate())}` +
    `T${pad(zoned.getHours())}:${pad(zoned.getMinutes())}`
  );
}

/** For display: "Tue, Sep 22, 4:00 PM EDT". */
export function formatInZone(instant: Date, timeZone: string): string {
  return new Intl.DateTimeFormat(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZoneName: "short",
    timeZone,
  }).format(instant);
}

/**
 * Clock time alone: "4:12 PM".
 *
 * For a list of stops, where the date is already established by the event above it and repeating it
 * on every row buries the one number that differs. Still zone-aware -- the organizer may be looking
 * at this from a different zone than the event is in, which is exactly the case that goes unnoticed.
 */
export function formatTimeInZone(instant: Date, timeZone: string): string {
  return new Intl.DateTimeFormat(undefined, {
    hour: "numeric",
    minute: "2-digit",
    timeZone,
  }).format(instant);
}

/**
 * Every IANA zone this browser knows, for the picker.
 *
 * `supportedValuesOf` is the browser's own list, so it cannot drift from what `TZDate` accepts
 * here -- though the *server* validates independently against Python's database, which is the
 * check that decides whether an event can be created (docs/design.md 6).
 */
export function knownTimeZones(): string[] {
  return Intl.supportedValuesOf("timeZone");
}
