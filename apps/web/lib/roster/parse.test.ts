/**
 * The paste parser's job is to survive whatever was in someone's spreadsheet, so the cases here are
 * shapes a real roster arrives in rather than a sweep of the API surface.
 */

import { describe, expect, it } from "vitest";

import { describeMapping, parseRoster } from "./parse";

describe("parseRoster", () => {
  it("reads a tab-separated paste from a spreadsheet", () => {
    const { rows, delimiter, usedHeader } = parseRoster(
      "Ana\t12 Oak St, Ann Arbor\nBo\t44 Elm Ave, Ann Arbor",
    );
    expect(delimiter).toBe("tab");
    expect(usedHeader).toBe(false);
    expect(rows).toHaveLength(2);
    expect(rows[0]).toMatchObject({ display_name: "Ana", address: "12 Oak St, Ann Arbor" });
    expect(rows[1]).toMatchObject({ display_name: "Bo", address: "44 Elm Ave, Ann Arbor" });
  });

  it("uses a header row when it recognises one", () => {
    const result = parseRoster("Address\tName\tSeats\n12 Oak St\tAna\t3");
    expect(result.usedHeader).toBe(true);
    expect(result.rows[0]).toMatchObject({
      display_name: "Ana",
      address: "12 Oak St",
      seats_available: 3,
      role: "driver",
    });
  });

  it("accepts header spellings a coordinator would actually type", () => {
    const result = parseRoster("Player,Home Address,Free Seats\nAna,12 Oak St,2");
    expect(result.usedHeader).toBe(true);
    expect(result.rows[0]).toMatchObject({ display_name: "Ana", seats_available: 2 });
  });

  it("does not mistake a data row for a header", () => {
    // "Name" as a person's address would be odd, but one incidental match must not eat a row.
    const result = parseRoster("Ana,12 Oak St\nBo,44 Elm Ave");
    expect(result.usedHeader).toBe(false);
    expect(result.rows).toHaveLength(2);
  });

  /**
   * The case that motivates quoted-CSV support at all: an address with commas is normal, and
   * splitting it naively turns one person into a broken row.
   */
  it("keeps a quoted address containing commas in one cell", () => {
    const { rows } = parseRoster('Ana,"123 Main St, Apt 4, Ann Arbor",2');
    expect(rows).toHaveLength(1);
    expect(rows[0].address).toBe("123 Main St, Apt 4, Ann Arbor");
    expect(rows[0].seats_available).toBe(2);
  });

  it("unescapes a doubled quote inside a quoted cell", () => {
    const { rows } = parseRoster('Ana,"The ""Big"" House, Ann Arbor"');
    expect(rows[0].address).toBe('The "Big" House, Ann Arbor');
  });

  it("infers driver from a seat count when no role column is present", () => {
    const { rows } = parseRoster("Ana\t12 Oak St\t3\nBo\t44 Elm Ave\t0");
    expect(rows[0]).toMatchObject({ role: "driver", seats_available: 3 });
    expect(rows[1]).toMatchObject({ role: "passenger", seats_available: 0 });
  });

  it("reads an explicit role column over the seat count", () => {
    const { rows } = parseRoster("Name,Address,Role,Seats\nAna,12 Oak St,passenger,3");
    expect(rows[0].role).toBe("passenger");
  });

  /**
   * The API returns 422 for a passenger holding seats (a deliberate rule -- Role.EITHER is the
   * correct way to say "has a car but would rather ride", and it is not surfaced in the MVP). The
   * parser reconciles rather than sending a row certain to fail.
   */
  it("zeroes seats for an explicit passenger so the API does not 422", () => {
    const { rows } = parseRoster("Name,Address,Role,Seats\nAna,12 Oak St,passenger,3");
    expect(rows[0]).toMatchObject({ role: "passenger", seats_available: 0 });
  });

  it("gives an explicit driver at least one seat", () => {
    const { rows } = parseRoster("Name,Address,Role,Seats\nAna,12 Oak St,driver,0");
    expect(rows[0]).toMatchObject({ role: "driver", seats_available: 1 });
  });

  it("reads yes/no under a Driver heading", () => {
    const { rows } = parseRoster("Name,Address,Driver\nAna,12 Oak St,yes\nBo,44 Elm Ave,no");
    expect(rows[0].role).toBe("driver");
    expect(rows[1].role).toBe("passenger");
  });

  it("picks up phone and email columns", () => {
    const { rows } = parseRoster(
      "Name,Address,Phone,Email\nAna,12 Oak St,555-0101,ana@example.com",
    );
    expect(rows[0]).toMatchObject({ phone: "555-0101", email: "ana@example.com" });
  });

  it("leaves absent contact fields null rather than empty strings", () => {
    const { rows } = parseRoster("Ana\t12 Oak St");
    expect(rows[0].phone).toBeNull();
    expect(rows[0].email).toBeNull();
  });

  /**
   * A partly-broken paste must import what it can. Rejecting forty rows because two are malformed
   * sends the coordinator back to the spreadsheet, which is the thing this is meant to beat.
   */
  it("imports the good rows and reports the bad ones by line number", () => {
    const { rows, skipped } = parseRoster("Ana\t12 Oak St\n\tno name here\nBo\t44 Elm Ave\nCarl\t");
    expect(rows.map((r) => r.display_name)).toEqual(["Ana", "Bo"]);
    expect(skipped).toHaveLength(2);
    expect(skipped[0].line).toBe(2);
    expect(skipped[1].line).toBe(4);
    expect(skipped[1].reason).toContain("Carl");
  });

  it("numbers lines against the pasted text, blank lines included", () => {
    const { rows } = parseRoster("Ana\t12 Oak St\n\n\nBo\t44 Elm Ave");
    expect(rows[0].line).toBe(1);
    expect(rows[1].line).toBe(4);
  });

  it("ignores trailing blank lines from a spreadsheet selection", () => {
    const { rows, skipped } = parseRoster("Ana\t12 Oak St\nBo\t44 Elm Ave\n\n\n");
    expect(rows).toHaveLength(2);
    expect(skipped).toHaveLength(0);
  });

  it("handles CRLF from a Windows spreadsheet", () => {
    const { rows } = parseRoster("Ana\t12 Oak St\r\nBo\t44 Elm Ave");
    expect(rows).toHaveLength(2);
    expect(rows[1].display_name).toBe("Bo");
  });

  it("rejects a seat count above what the API accepts", () => {
    const { rows, skipped } = parseRoster("Ana\t12 Oak St\t40");
    expect(rows).toHaveLength(0);
    expect(skipped[0].reason).toContain("40 seats");
  });

  it("rejects a negative seat count", () => {
    const { skipped } = parseRoster("Ana\t12 Oak St\t-2");
    expect(skipped[0].reason).toContain("negative");
  });

  it("returns nothing for empty input without throwing", () => {
    expect(parseRoster("")).toMatchObject({ rows: [], skipped: [] });
    expect(parseRoster("   \n  \n")).toMatchObject({ rows: [], skipped: [] });
  });

  it("truncates rather than rejecting an over-long name", () => {
    const { rows } = parseRoster(`${"A".repeat(200)}\t12 Oak St`);
    expect(rows[0].display_name).toHaveLength(120);
  });
});

describe("describeMapping", () => {
  it("says which columns were read and where the mapping came from", () => {
    expect(describeMapping(parseRoster("Name,Address,Seats\nAna,12 Oak St,2"))).toBe(
      "Read name, address, seats — from the header row.",
    );
    expect(describeMapping(parseRoster("Ana\t12 Oak St"))).toBe(
      "Read name, address — by position.",
    );
  });
});
