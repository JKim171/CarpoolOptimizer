"use client";

/**
 * A date, then hour : minute and AM/PM, standing in for `<input type="datetime-local">`.
 *
 * The native control renders its time as `--:-- --`, which tells nobody what to type, and leaves
 * the meridiem blank until it is set -- so "4:00" was not a time until someone found the third
 * segment. Here the hour and minute carry placeholders, and the meridiem starts at PM, because
 * the events this is for (a practice, a rehearsal, a game) are overwhelmingly afternoon and
 * evening ones.
 *
 * It reports the same "YYYY-MM-DDTHH:mm" the native input did, or "" while incomplete, so the
 * zone handling in `lib/time.ts` is untouched.
 */

import { useState } from "react";

import { Select, TextInput } from "@/components/ui/controls";
import { type Meridiem, twelveHourToWallClock } from "@/lib/time";

export function WallClockInput({
  label,
  onChange,
}: {
  /** Names the hour, minute and AM/PM boxes for a screen reader; the enclosing `Field` labels only the date. */
  label: string;
  onChange: (value: string) => void;
}) {
  const [date, setDate] = useState("");
  const [hour, setHour] = useState("");
  const [minute, setMinute] = useState("");
  const [meridiem, setMeridiem] = useState<Meridiem>("PM");

  function update(
    next: Partial<{ date: string; hour: string; minute: string; meridiem: Meridiem }>,
  ) {
    const parts = { date, hour, minute, meridiem, ...next };
    setDate(parts.date);
    setHour(parts.hour);
    setMinute(parts.minute);
    setMeridiem(parts.meridiem);
    onChange(twelveHourToWallClock(parts.date, parts.hour, parts.minute, parts.meridiem));
  }

  const digits = (value: string) => value.replace(/\D/g, "").slice(0, 2);

  return (
    <div className="flex flex-wrap items-center gap-2">
      <div className="min-w-[9.5rem] flex-1">
        <TextInput
          type="date"
          value={date}
          onChange={(event) => update({ date: event.target.value })}
          required
        />
      </div>
      <div className="flex items-center gap-1">
        <div className="w-14">
          <TextInput
            aria-label={`${label}, hour`}
            inputMode="numeric"
            placeholder="hh"
            value={hour}
            onChange={(event) => update({ hour: digits(event.target.value) })}
            required
          />
        </div>
        <span className="text-ink-muted" aria-hidden>
          :
        </span>
        <div className="w-14">
          <TextInput
            aria-label={`${label}, minute`}
            inputMode="numeric"
            placeholder="mm"
            value={minute}
            onChange={(event) => update({ minute: digits(event.target.value) })}
          />
        </div>
        <div className="w-[4.5rem]">
          <Select
            aria-label={`${label}, AM or PM`}
            value={meridiem}
            onChange={(event) => update({ meridiem: event.target.value as Meridiem })}
          >
            <option value="AM">AM</option>
            <option value="PM">PM</option>
          </Select>
        </div>
      </div>
    </div>
  );
}
