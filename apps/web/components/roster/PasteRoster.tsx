"use client";

/**
 * Bulk roster entry by pasting from a spreadsheet.
 *
 * This is the feature that decides whether the product beats what the coordinator does today. They
 * arrive with the roster already in Sheets; a form that takes forty names one at a time is slower
 * than the status quo, so the paste path is the primary way a roster gets in and the single-row
 * form is the fallback.
 *
 * Three stages, because each can fail differently and a coordinator needs to see which: parse the
 * text, resolve the addresses, then write the rows. Nothing is sent until the preview has been
 * seen -- a silent import of forty misread rows is far worse than a slow one.
 */

import { useState } from "react";

import { Button, Panel, Problem } from "@/components/ui/controls";
import { ApiError } from "@/lib/api/client";
import { resolve, type Resolution } from "@/lib/api/geocode";
import { addParticipant, type ParticipantCreate } from "@/lib/api/participants";
import { describeMapping, parseRoster, type ParsedParticipant } from "@/lib/roster/parse";

const EXAMPLE = "Ana Ruiz\t12 Oak St, Ann Arbor\t3\nBo Chen\t44 Elm Ave, Ann Arbor\t0";

type Candidate = {
  parsed: ParsedParticipant;
  resolution: Resolution | null;
};

type Failure = { name: string; reason: string };

export function PasteRoster({
  publicId,
  seatsLeft,
  onImported,
}: {
  publicId: string;
  seatsLeft: number;
  onImported: () => void;
}) {
  const [text, setText] = useState("");
  const [candidates, setCandidates] = useState<Candidate[] | null>(null);
  const [parseSummary, setParseSummary] = useState<string>("");
  const [skipped, setSkipped] = useState<{ line: number; reason: string }[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [failures, setFailures] = useState<Failure[]>([]);
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null);

  const reset = () => {
    setCandidates(null);
    setParseSummary("");
    setSkipped([]);
    setFailures([]);
    setProgress(null);
    setError(null);
  };

  async function preview() {
    setError(null);
    setFailures([]);
    const result = parseRoster(text);
    setParseSummary(describeMapping(result));
    setSkipped(result.skipped);

    if (result.rows.length === 0) {
      setCandidates([]);
      return;
    }

    setBusy(true);
    try {
      // One batch call for the whole paste: the endpoint is cache-first, and forty separate
      // requests would spend the shared daily quota forty times over for a roster that mostly
      // repeats the same few streets.
      const resolutions = await resolve(result.rows.map((r) => r.address));
      setCandidates(
        result.rows.map((parsed, i) => ({ parsed, resolution: resolutions[i] ?? null })),
      );
    } catch (e) {
      // A geocoder outage must not block roster entry -- addresses can still be added one at a
      // time with a pin placed by hand.
      setError(
        e instanceof ApiError
          ? `Could not look up addresses: ${e.message}`
          : "Could not look up addresses.",
      );
      setCandidates(null);
    } finally {
      setBusy(false);
    }
  }

  const resolved = (candidates ?? []).filter((c) => c.resolution?.place);
  const unresolved = (candidates ?? []).filter((c) => !c.resolution?.place);
  const approximate = resolved.filter((c) => c.resolution!.place!.is_approximate);
  const overCap = resolved.length > seatsLeft;

  async function importRows() {
    setBusy(true);
    setError(null);
    const failed: Failure[] = [];
    let done = 0;
    setProgress({ done: 0, total: resolved.length });

    // Sequential: the cap is enforced by a version bump that takes the event row's lock, so
    // parallel writes serialize on the server anyway -- and firing forty at once turns one
    // rejected row into forty ambiguous failures.
    for (const { parsed, resolution } of resolved) {
      const place = resolution!.place!;
      const body: ParticipantCreate = {
        display_name: parsed.display_name,
        role: parsed.role,
        seats_available: parsed.seats_available,
        phone: parsed.phone,
        email: parsed.email,
        pickup: { address: place.address, lat: place.lat, lng: place.lng },
        // The generated types require every field that carries a server-side default, so these are
        // stated rather than omitted. Both legs by default is design 2.4's "same riders both ways";
        // a paste has no way to express otherwise, and the row can be edited after.
        needs_outbound: true,
        needs_return: true,
        priority: 0,
      };
      try {
        await addParticipant(publicId, body);
      } catch (e) {
        failed.push({
          name: parsed.display_name,
          reason: e instanceof ApiError ? e.message : "Could not be added.",
        });
      }
      done += 1;
      setProgress({ done, total: resolved.length });
    }

    setBusy(false);
    setFailures(failed);
    onImported();

    if (failed.length === 0) {
      setText("");
      reset();
    } else {
      setCandidates(null);
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <label className="block">
        <span className="text-sm font-medium text-ink">Paste a roster</span>
        <span className="mt-1 block text-xs text-ink-muted">
          Copy the rows straight out of a spreadsheet. Name and address are required; a seats column
          marks who drives. A header row is used if there is one.
        </span>
        <textarea
          value={text}
          onChange={(e) => {
            setText(e.target.value);
            if (candidates) reset();
          }}
          rows={5}
          spellCheck={false}
          placeholder={EXAMPLE}
          className="mt-2 w-full rounded-md border border-line bg-surface-raised px-3 py-2 font-mono text-xs text-ink placeholder:text-ink-muted hover:border-line-strong"
        />
      </label>

      <div className="flex items-center gap-3">
        <Button type="button" onClick={preview} disabled={busy || text.trim() === ""}>
          {busy && !progress ? "Looking up addresses…" : "Preview"}
        </Button>
        {candidates && (
          <Button type="button" variant="quiet" onClick={reset} disabled={busy}>
            Clear
          </Button>
        )}
        {progress && (
          <span className="text-sm text-ink-muted">
            Adding {progress.done} of {progress.total}…
          </span>
        )}
      </div>

      {error && <Problem>{error}</Problem>}

      {failures.length > 0 && (
        <Problem>
          <span className="font-medium">
            {failures.length} {failures.length === 1 ? "row" : "rows"} could not be added:
          </span>
          <ul className="mt-1 list-disc pl-5">
            {failures.map((f, i) => (
              <li key={i}>
                {f.name} — {f.reason}
              </li>
            ))}
          </ul>
        </Problem>
      )}

      {candidates && (
        <Panel className="flex flex-col gap-3">
          <p className="text-xs text-ink-muted">{parseSummary}</p>

          {candidates.length === 0 && (
            <p className="text-sm text-ink">Nothing to import from that paste.</p>
          )}

          {skipped.length > 0 && (
            <div className="text-sm">
              <p className="font-medium text-warn-ink">
                {skipped.length} {skipped.length === 1 ? "row" : "rows"} skipped
              </p>
              <ul className="mt-1 list-disc pl-5 text-ink-muted">
                {skipped.map((s) => (
                  <li key={s.line}>
                    Line {s.line}: {s.reason}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {candidates.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="text-xs uppercase tracking-wide text-ink-muted">
                  <tr>
                    <th className="py-1 pr-3 font-medium">Name</th>
                    <th className="py-1 pr-3 font-medium">Pickup</th>
                    <th className="py-1 pr-3 font-medium">Role</th>
                    <th className="py-1 font-medium">Seats</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {candidates.map((c) => {
                    const place = c.resolution?.place;
                    return (
                      <tr key={c.parsed.line}>
                        <td className="py-1.5 pr-3 text-ink">{c.parsed.display_name}</td>
                        <td className="py-1.5 pr-3">
                          {place ? (
                            <>
                              <span className="text-ink">{place.address}</span>
                              {place.is_approximate && (
                                <span className="ml-2 text-xs text-warn-ink">approximate</span>
                              )}
                            </>
                          ) : (
                            <span className="text-danger-ink">
                              No match for “{c.parsed.address}”
                            </span>
                          )}
                        </td>
                        <td className="py-1.5 pr-3 text-ink-muted">{c.parsed.role}</td>
                        <td className="py-1.5 text-ink-muted">{c.parsed.seats_available}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {unresolved.length > 0 && (
            <p className="text-sm text-ink-muted">
              {unresolved.length} {unresolved.length === 1 ? "address" : "addresses"} could not be
              found and will be left out. Add those people individually and place the pin by hand.
            </p>
          )}

          {approximate.length > 0 && (
            <p className="text-sm text-warn-ink">
              {approximate.length} {approximate.length === 1 ? "address is" : "addresses are"} only
              approximate. Check those pins on the map after importing.
            </p>
          )}

          {overCap && (
            <Problem>
              That is {resolved.length} people and there {seatsLeft === 1 ? "is" : "are"}{" "}
              {seatsLeft} {seatsLeft === 1 ? "place" : "places"} left on this roster.
            </Problem>
          )}

          {resolved.length > 0 && (
            <div>
              <Button type="button" onClick={importRows} disabled={busy || overCap}>
                Add {resolved.length} {resolved.length === 1 ? "person" : "people"}
              </Button>
            </div>
          )}
        </Panel>
      )}
    </div>
  );
}
