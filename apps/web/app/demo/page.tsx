/**
 * A finished example, public and indexable: the one page that shows a result without asking for a
 * roster first.
 *
 * A server component for the same reason as the landing page -- `metadata` cannot be exported from
 * a client component -- with the screen itself in `DemoDashboard`. The people in it are generated
 * (`carpool_api.demo`), so unlike an event page there is nothing here to keep out of an index.
 */

import type { Metadata } from "next";

import { DemoDashboard } from "@/components/DemoDashboard";
import { demoHeadcount } from "@/lib/demo/event";

export const metadata: Metadata = {
  title: "An example carpool plan",
  description: `A club practice with ${demoHeadcount()}: see who drives who, in what pickup order, there and back.`,
  alternates: { canonical: "/demo" },
};

export default function Demo() {
  return <DemoDashboard />;
}
