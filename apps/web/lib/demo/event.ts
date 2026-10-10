/**
 * The example event behind `/demo`, read from the file `make demo` generates.
 *
 * The file is produced by the API's own solver and response models (`carpool_api.demo`) and checked
 * against them by `test_demo.py`, so the solution in it has the shape a real one does and renders
 * through the same components. Only the wrapper around it is typed by hand here, because it is not
 * an API route and so does not appear in the generated schema.
 */

import type { Solution } from "@/lib/api/solutions";

import data from "./event.json";

export type DemoPerson = {
  id: string;
  display_name: string;
  role: "driver" | "passenger";
  lat: number;
  lng: number;
};

export type DemoEvent = {
  name: string;
  venue: { address: string; lat: number; lng: number };
  time_zone: string;
  arrival_at: string;
  ends_at: string;
  people: DemoPerson[];
  solution: Solution;
};

export const demoEvent = data as DemoEvent;

/** "12 players, 4 of them driving" -- counted from the file, so a regenerated example stays true. */
export function demoHeadcount(): string {
  const drivers = demoEvent.people.filter((p) => p.role === "driver").length;
  return `${demoEvent.people.length} players, ${drivers} of them driving`;
}
