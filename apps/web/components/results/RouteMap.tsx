"use client";

/**
 * The solution on a map: one coloured path per car, stops numbered in the order they are driven.
 *
 * **The lines are schematic, not driving directions.** They join consecutive stops in a straight
 * line, because route geometry is deliberately never fetched per solve -- the provider's directions
 * quota binds long before the matrix quota (docs/design.md 4.4), and a solution is re-solved far
 * more often than it is driven. The map answers "does this ordering make sense", which is a
 * question straight lines answer perfectly well: a car doubling back across town looks wrong at a
 * glance whether or not the line follows a road. Turn-by-turn is the Google Maps link per leg, one
 * request, at the moment a driver actually needs it. The caption on screen says so, because a line
 * between two points on a map otherwise reads as a road.
 */

import { Map as MapLibreMap, Marker, NavigationControl, type GeoJSONSource } from "maplibre-gl";
import { useEffect, useRef, useState } from "react";

import { FALLBACK_CENTER, STYLE } from "@/components/map/basemap";
import { DESTINATION_COLOR, routeColor } from "@/lib/results/colors";

import "maplibre-gl/dist/maplibre-gl.css";

/** `number` is the 1-based stop a person reads, already converted by the caller. */
export type MappedStop = { number: number; label: string; lat: number; lng: number };

/** One car's leg, already resolved to coordinates by the caller. */
export type MappedRoute = {
  routeId: string;
  driverName: string;
  /** The driver's own home. Null when it could not be located -- see `ResultsPanel`. */
  home: { lat: number; lng: number } | null;
  stops: MappedStop[];
};

export type Venue = { address: string; lat: number; lng: number };

const SOURCE = "routes";
const LAYER = "route-lines";

function dot(color: string, label: string, text: string): HTMLDivElement {
  const el = document.createElement("div");
  el.style.cssText = [
    "display:flex",
    "align-items:center",
    "justify-content:center",
    "width:22px",
    "height:22px",
    "border-radius:9999px",
    `background:${color}`,
    "border:2px solid white",
    "box-shadow:0 1px 3px rgba(0,0,0,.4)",
    "color:white",
    "font:600 11px/1 ui-sans-serif,system-ui,sans-serif",
  ].join(";");
  el.textContent = text;
  el.title = label;
  return el;
}

/** The venue is a rounded square, so it is distinguishable without relying on colour alone. */
function venueMarker(label: string): HTMLDivElement {
  const el = dot(DESTINATION_COLOR, label, "");
  el.style.borderRadius = "4px";
  el.style.width = "18px";
  el.style.height = "18px";
  return el;
}

/** A driver's home: the same colour as their car, hollow, so it is not mistaken for a pickup. */
function homeMarker(color: string, label: string): HTMLDivElement {
  const el = dot("white", label, "");
  el.style.border = `3px solid ${color}`;
  el.style.width = "16px";
  el.style.height = "16px";
  return el;
}

/**
 * The path a car drives on this leg: home to each stop to the venue, or the reverse on the return.
 * Built from the same ordering the list shows, so the two cannot disagree.
 */
function pathOf(route: MappedRoute, venue: Venue, leg: "outbound" | "inbound"): [number, number][] {
  const stops: [number, number][] = route.stops.map((s) => [s.lng, s.lat]);
  const venuePoint: [number, number] = [venue.lng, venue.lat];
  const home: [number, number] | null = route.home ? [route.home.lng, route.home.lat] : null;

  const points =
    leg === "outbound"
      ? [...(home ? [home] : []), ...stops, venuePoint]
      : [venuePoint, ...stops, ...(home ? [home] : [])];
  return points;
}

export function RouteMap({
  routes,
  venue,
  leg,
  highlightedRouteId,
  className,
}: {
  routes: MappedRoute[];
  venue: Venue | null;
  leg: "outbound" | "inbound";
  highlightedRouteId: string | null;
  className?: string;
}) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<MapLibreMap | null>(null);
  const markers = useRef<Marker[]>([]);
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!container.current || map.current) return;
    const held = markers.current;

    const instance = new MapLibreMap({
      container: container.current,
      style: STYLE,
      center: venue ? [venue.lng, venue.lat] : FALLBACK_CENTER,
      zoom: 11,
      attributionControl: { compact: true },
    });
    instance.addControl(new NavigationControl({ showCompass: false }), "top-right");
    instance.on("load", () => {
      instance.addSource(SOURCE, {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      instance.addLayer({
        id: LAYER,
        type: "line",
        source: SOURCE,
        layout: { "line-cap": "round", "line-join": "round" },
        paint: {
          "line-color": ["get", "color"],
          "line-width": ["get", "width"],
          "line-opacity": ["get", "opacity"],
        },
      });
      setReady(true);
    });
    instance.on("error", (event) => {
      if (event.error?.message?.includes("style")) setFailed(true);
    });

    map.current = instance;
    return () => {
      instance.remove();
      map.current = null;
      held.forEach((m) => m.remove());
      markers.current = [];
      setReady(false);
    };
    // Built once; data changes update the source and the markers rather than rebuilding the map.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Lines. One feature per car, restyled rather than rebuilt when the highlight moves.
  useEffect(() => {
    const instance = map.current;
    if (!instance || !ready || !venue) return;
    const source = instance.getSource<GeoJSONSource>(SOURCE);
    if (!source) return;

    const dimmed = highlightedRouteId !== null;
    source.setData({
      type: "FeatureCollection",
      features: routes.map((route, index) => {
        const on = route.routeId === highlightedRouteId;
        return {
          type: "Feature" as const,
          properties: {
            color: routeColor(index),
            width: on ? 6 : 3.5,
            opacity: dimmed && !on ? 0.25 : 0.9,
          },
          geometry: { type: "LineString" as const, coordinates: pathOf(route, venue, leg) },
        };
      }),
    });
  }, [routes, venue, leg, highlightedRouteId, ready]);

  // Markers. Rebuilt wholesale: they are few, and a solution changing is a new answer rather than
  // an edit to the old one, so there is no drag or hover state worth preserving across it.
  useEffect(() => {
    const instance = map.current;
    if (!instance || !ready) return;

    markers.current.forEach((m) => m.remove());
    markers.current = [];

    if (venue) {
      markers.current.push(
        new Marker({ element: venueMarker(`Destination — ${venue.address}`) })
          .setLngLat([venue.lng, venue.lat])
          .addTo(instance),
      );
    }

    routes.forEach((route, index) => {
      const color = routeColor(index);
      if (route.home) {
        markers.current.push(
          new Marker({ element: homeMarker(color, `${route.driverName} (home)`) })
            .setLngLat([route.home.lng, route.home.lat])
            .addTo(instance),
        );
      }
      route.stops.forEach((stop) => {
        markers.current.push(
          new Marker({
            element: dot(color, `${stop.label} — ${route.driverName}`, String(stop.number)),
          })
            .setLngLat([stop.lng, stop.lat])
            .addTo(instance),
        );
      });
    });
  }, [routes, venue, leg, ready]);

  // Fit to everything once, and again whenever the answer changes -- but not on a highlight, which
  // would move the thing being pointed at.
  useEffect(() => {
    const instance = map.current;
    if (!instance || !ready) return;
    const points: [number, number][] = routes.flatMap((route) => [
      ...route.stops.map((s): [number, number] => [s.lng, s.lat]),
      ...(route.home ? [[route.home.lng, route.home.lat] as [number, number]] : []),
    ]);
    if (venue) points.push([venue.lng, venue.lat]);
    if (points.length === 0) return;
    if (points.length === 1) {
      instance.easeTo({ center: points[0], zoom: 14 });
      return;
    }
    const lngs = points.map((p) => p[0]);
    const lats = points.map((p) => p[1]);
    instance.fitBounds(
      [
        [Math.min(...lngs), Math.min(...lats)],
        [Math.max(...lngs), Math.max(...lats)],
      ],
      { padding: 48, maxZoom: 15, duration: 400 },
    );
  }, [routes, venue, ready]);

  return (
    <div className={className}>
      <div
        ref={container}
        className="h-96 w-full overflow-hidden rounded-md border border-line bg-surface-sunken"
        role="application"
        aria-label="Each car's route, with stops numbered in pickup order."
      />
      <p className="mt-1 text-xs text-ink-muted">
        {failed
          ? "The map could not load. Every car and stop is listed below in order."
          : "Lines join stops directly and are not driving directions — use a car's Google Maps link for those."}
      </p>
    </div>
  );
}
