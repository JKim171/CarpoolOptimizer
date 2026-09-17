/**
 * Parse a roster pasted out of a spreadsheet.
 *
 * The bar this slice has to clear is "faster than the spreadsheet the coordinator uses today"
 * (docs/roadmap.md). A coordinator arrives with forty rows already in Sheets; retyping them into a
 * form is slower than what they do now, so the paste path is the feature and the form is the
 * fallback.
 *
 * Pure on purpose -- no fetch, no DOM, no clock. It turns text into rows and complaints, and the
 * component decides what to do about them. That is what makes the interesting part testable, which
 * matters because the input is whatever a human had in a spreadsheet.
 *
 * What it does NOT do: geocode, deduplicate against the existing roster, or enforce the participant
 * cap. Those need the server.
 */

export type ParsedRole = "driver" | "passenger";

export type ParsedParticipant = {
  display_name: string;
  address: string;
  role: ParsedRole;
  seats_available: number;
  phone: string | null;
  email: string | null;
  /** 1-based line in the pasted text, so a complaint can point at the row the human sees. */
  line: number;
};

export type SkippedRow = {
  line: number;
  text: string;
  reason: string;
};

export type ParseResult = {
  rows: ParsedParticipant[];
  skipped: SkippedRow[];
  /** Which column each field was read from, so the UI can show how the paste was understood. */
  mapping: Partial<Record<Field, number>>;
  /** True when the first line was consumed as a header rather than data. */
  usedHeader: boolean;
  delimiter: "tab" | "comma";
};

type Field = "display_name" | "address" | "role" | "seats_available" | "phone" | "email";

/**
 * Header spellings seen in the wild, lowercased. A coordinator's sheet says "Name" or "Player" or
 * "Who"; insisting on one spelling would send them back to retyping.
 */
const HEADERS: Record<Field, string[]> = {
  display_name: ["name", "display name", "player", "person", "who", "participant", "full name"],
  address: ["address", "home", "home address", "pickup", "pickup address", "location", "street"],
  role: ["role", "driver", "driving", "type"],
  seats_available: ["seats", "seats available", "capacity", "spots", "car seats", "free seats"],
  phone: ["phone", "mobile", "cell", "number", "phone number"],
  email: ["email", "e-mail", "email address"],
};

/** Positional fallback when there is no header row: what a bare two-or-three column paste means. */
const POSITIONAL: Field[] = ["display_name", "address", "seats_available", "phone", "email"];

const MAX_NAME = 120;
const MAX_ADDRESS = 500;
const MAX_SEATS = 8;

/**
 * Split one line into cells.
 *
 * Quoted CSV is handled because "123 Main St, Apt 4, Ann Arbor" is an ordinary address and a naive
 * split on commas turns one person into three broken columns.
 */
function splitLine(line: string, delimiter: "tab" | "comma"): string[] {
  if (delimiter === "tab") return line.split("\t").map((c) => c.trim());

  const cells: string[] = [];
  let cell = "";
  let quoted = false;
  for (let i = 0; i < line.length; i += 1) {
    const ch = line[i];
    if (quoted) {
      if (ch === '"') {
        // A doubled quote inside a quoted cell is an escaped quote, per RFC 4180.
        if (line[i + 1] === '"') {
          cell += '"';
          i += 1;
        } else {
          quoted = false;
        }
      } else {
        cell += ch;
      }
    } else if (ch === '"') {
      quoted = true;
    } else if (ch === ",") {
      cells.push(cell.trim());
      cell = "";
    } else {
      cell += ch;
    }
  }
  cells.push(cell.trim());
  return cells;
}

function detectDelimiter(lines: string[]): "tab" | "comma" {
  // A spreadsheet paste is tab-separated; a saved CSV is not. Any tab at all settles it, because an
  // address never contains one.
  return lines.some((l) => l.includes("\t")) ? "tab" : "comma";
}

function matchHeader(cell: string): Field | null {
  const norm = cell.trim().toLowerCase().replace(/_/g, " ");
  for (const [field, spellings] of Object.entries(HEADERS) as [Field, string[]][]) {
    if (spellings.includes(norm)) return field;
  }
  return null;
}

/** A header row is one where at least two cells are recognisable field names. */
function readHeader(cells: string[]): Partial<Record<Field, number>> | null {
  const mapping: Partial<Record<Field, number>> = {};
  let hits = 0;
  cells.forEach((cell, index) => {
    const field = matchHeader(cell);
    if (field && mapping[field] === undefined) {
      mapping[field] = index;
      hits += 1;
    }
  });
  return hits >= 2 ? mapping : null;
}

/**
 * Read a role cell.
 *
 * Returns `null` for "no opinion expressed" rather than defaulting, so that seat count can decide.
 * A sheet that says "yes" under a "Driver" heading means driver; the same "yes" under "Role" is
 * meaningless, but harmless to read the same way.
 */
function readRole(raw: string | undefined): ParsedRole | null {
  if (!raw) return null;
  const v = raw.trim().toLowerCase();
  if (["driver", "d", "drive", "driving", "yes", "y", "true", "1"].includes(v)) return "driver";
  if (["passenger", "p", "rider", "ride", "no", "n", "false", "0"].includes(v)) return "passenger";
  return null;
}

function readSeats(raw: string | undefined): number | null {
  if (!raw) return null;
  const digits = raw.trim().match(/-?\d+/);
  if (!digits) return null;
  return Number.parseInt(digits[0], 10);
}

/**
 * Parse pasted roster text.
 *
 * Never throws: a bad row becomes a `skipped` entry with a reason the coordinator can act on. A
 * paste of forty rows where two are malformed should import thirty-eight and say which two, rather
 * than rejecting the lot.
 */
export function parseRoster(text: string): ParseResult {
  const rawLines = text.split(/\r\n|\r|\n/);
  const nonEmpty = rawLines.filter((l) => l.trim() !== "");
  const delimiter = detectDelimiter(nonEmpty);

  const rows: ParsedParticipant[] = [];
  const skipped: SkippedRow[] = [];

  let mapping: Partial<Record<Field, number>> | null = null;
  let usedHeader = false;
  let started = false;

  rawLines.forEach((line, index) => {
    const lineNumber = index + 1;
    if (line.trim() === "") return;

    const cells = splitLine(line, delimiter);

    if (!started) {
      started = true;
      const header = readHeader(cells);
      if (header) {
        mapping = header;
        usedHeader = true;
        return;
      }
      mapping = Object.fromEntries(
        POSITIONAL.slice(0, Math.max(cells.length, 2)).map((f, i) => [f, i]),
      );
    }

    const at = (field: Field): string | undefined => {
      const index = mapping?.[field];
      return index === undefined ? undefined : cells[index];
    };

    const name = (at("display_name") ?? "").trim();
    const address = (at("address") ?? "").trim();

    if (!name && !address) {
      skipped.push({ line: lineNumber, text: line, reason: "No name or address in this row." });
      return;
    }
    if (!name) {
      skipped.push({ line: lineNumber, text: line, reason: "No name in this row." });
      return;
    }
    if (!address) {
      skipped.push({ line: lineNumber, text: line, reason: `No address for ${name}.` });
      return;
    }

    const seatsRaw = readSeats(at("seats_available"));
    const roleRaw = readRole(at("role"));

    // Seats decide the role when nothing said otherwise: a sheet with a seats column and no role
    // column is the common shape, and "3" there plainly means this person drives.
    const role: ParsedRole =
      roleRaw ?? (seatsRaw !== null && seatsRaw > 0 ? "driver" : "passenger");
    let seats = seatsRaw ?? 0;

    if (seats < 0) {
      skipped.push({ line: lineNumber, text: line, reason: `${name}: seats cannot be negative.` });
      return;
    }
    if (seats > MAX_SEATS) {
      skipped.push({
        line: lineNumber,
        text: line,
        reason: `${name}: ${seats} seats is more than the ${MAX_SEATS} the API accepts.`,
      });
      return;
    }

    // The API rejects a passenger holding seats (a 422), so reconcile here rather than sending a
    // row that is certain to fail. Someone with a car who would rather ride is what Role.EITHER is
    // for, and that role is not surfaced in the MVP -- so the honest reading of "passenger, 3
    // seats" is that the seats were not meant as an offer to drive.
    if (role === "passenger" && seats > 0) seats = 0;
    if (role === "driver" && seats === 0) seats = 1;

    rows.push({
      display_name: name.slice(0, MAX_NAME),
      address: address.slice(0, MAX_ADDRESS),
      role,
      seats_available: seats,
      phone: (at("phone") ?? "").trim() || null,
      email: (at("email") ?? "").trim() || null,
      line: lineNumber,
    });
  });

  return { rows, skipped, mapping: mapping ?? {}, usedHeader, delimiter };
}

/** Human description of how a paste was read, for the preview header. */
export function describeMapping(result: ParseResult): string {
  const names: Record<Field, string> = {
    display_name: "name",
    address: "address",
    role: "role",
    seats_available: "seats",
    phone: "phone",
    email: "email",
  };
  const ordered = (Object.entries(result.mapping) as [Field, number][])
    .sort((a, b) => a[1] - b[1])
    .map(([field]) => names[field]);
  const source = result.usedHeader ? "from the header row" : "by position";
  return ordered.length > 0 ? `Read ${ordered.join(", ")} — ${source}.` : "Nothing recognised.";
}
