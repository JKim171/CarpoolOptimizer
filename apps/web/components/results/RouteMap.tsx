"use client";

/**
 * The solution on a map: one coloured path per car, stops numbered in the order they are driven.
 *
 * **A leg follows the roads when its geometry has arrived, and joins its stops directly until
 * then.** Geometry is never fetched per solve -- the provider's directions quota binds long before
 * the matrix quota (docs/design.md 4.4) -- but the first time a solution is viewed, and stored
 * after. The straight lines are what the map shows while that request is in flight, for a leg the
 * provider could not draw, and on the generated `/demo` event, which has no real roads to follow.
 * They are still a fair picture of the ordering: a car doubling back across town looks wrong at a
 * glance either way. The caption says which kind of line is on screen, because a straight line on a
 * map otherwise reads as a road. Turn-by-turn remains the Google Maps link per leg.
 */

import { Map as MapLibreMap, Marker, NavigationControl, type GeoJSONSource } from "maplibre-gl";
import { useEffect, useRef, useState, type ReactNode } from "react";

import { FALLBACK_CENTER, styleFor } from "@/components/map/basemap";
import { applyMapPalette } from "@/components/map/palette";
import { MapFrame } from "@/components/map/MapFrame";
import { homePin, stopPin, venuePin } from "@/components/map/markers";
import { useLiveColorScheme } from "@/lib/colorScheme";
import { routeColor } from "@/lib/results/colors";

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
  /** This leg along the roads, as [lng, lat] pairs. Absent or null: join the stops directly. */
  road?: [number, number][] | null;
};

export type Venue = { address: string; lat: number; lng: number };

const SOURCE = "routes";
const LAYER = "route-lines";

/**
 * Attach the route-line source and layer to whatever style is currently loaded.
 *
 * Called from `style.load` rather than `load`, because `setStyle` discards every source and layer
 * the app added and fires `style.load` again when the replacement is ready. Doing this on `load`
 * only would leave the map with no lines the first time the theme changed.
 */
function addRouteLayer(instance: MapLibreMap): void {
  if (instance.getSource(SOURCE)) return;
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
}

/**
 * The path a car drives on this leg: home to each stop to the venue, or the reverse on the return.
 * The road line when there is one -- the API draws it through the same stored ordering the list
 * shows -- and otherwise straight segments built from that ordering here.
 */
function pathOf(route: MappedRoute, venue: Venue, leg: "outbound" | "inbound"): [number, number][] {
  if (route.road) return route.road;
  const stops: [number, number][] = route.stops.map((s) => [s.lng, s.lat]);
  const venuePoint: [number, number] = [venue.lng, venue.lat];
  const home: [number, number] | null = route.home ? [route.home.lng, route.home.lat] : null;

  const points =
    leg === "outbound"
      ? [...(home ? [home] : []), ...stops, venuePoint]
      : [venuePoint, ...stops, ...(home ? [home] : [])];
  return points;
}

/** Says which kind of line is on screen, since a straight one otherwise reads as a road. */
function captionFor(routes: MappedRoute[]): string {
  const onRoads = routes.filter((route) => route.road).length;
  if (onRoads > 0 && onRoads === routes.length) {
    return "Lines follow the roads — a car's Google Maps link has turn-by-turn directions.";
  }
  if (onRoads > 0) {
    return "Lines follow the roads where directions loaded and join stops directly elsewhere — use a car's Google Maps link for turn-by-turn.";
  }
  return "Lines join stops directly and are not driving directions — use a car's Google Maps link for those.";
}

export function RouteMap({
  routes,
  venue,
  leg,
  highlightedRouteId,
  overlay,
}: {
  routes: MappedRoute[];
  venue: Venue | null;
  leg: "outbound" | "inbound";
  highlightedRouteId: string | null;
  /** Controls drawn over the map -- the canvas's mode switch. */
  overlay?: ReactNode;
}) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<MapLibreMap | null>(null);
  const markers = useRef<Marker[]>([]);
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);
  const scheme = useLiveColorScheme();
  /** Which basemap the live instance is actually showing, so the effect below is a no-op at mount. */
  const applied = useRef(scheme);

  useEffect(() => {
    if (!container.current || map.current) return;
    const held = markers.current;

    const instance = new MapLibreMap({
      container: container.current,
      style: styleFor(applied.current),
      center: venue ? [venue.lng, venue.lat] : FALLBACK_CENTER,
      zoom: 11,
      attributionControl: { compact: true },
    });
    instance.addControl(new NavigationControl({ showCompass: false }), "top-right");
    // `style.load`, not `load`: it fires for the first style *and* for every one `setStyle` swaps
    // in, which is what keeps the lines alive across a theme change.
    instance.on("style.load", () => {
      applyMapPalette(instance, applied.current);
      addRouteLayer(instance);
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

  /**
   * Swap the basemap when the system theme changes under a running page.
   *
   * `ready` goes false for the moment the new style is in flight: the data effects below are
   * guarded by it, so they do not write to a source that `setStyle` has just discarded. The
   * `style.load` handler above puts the layer back and flips it true, which re-runs them.
   */
  useEffect(() => {
    const instance = map.current;
    if (!instance || applied.current === scheme) return;
    applied.current = scheme;
    setReady(false);
    instance.setStyle(styleFor(scheme));
  }, [scheme]);

  // Lines. One feature per car, restyled rather than rebuilt when the highlight moves.
  useEffect(() => {
    const instance = map.current;
    if (!instance || !ready || !venue) return;
    const source = instance.getSource<GeoJSONSource>(SOURCE);
    if (!source) return;

    // Dim only for a highlight that names a car actually on this map. A re-optimize replaces every
    // route id, so a highlight held across one would otherwise match nothing and fade *all* of
    // them at once -- the same misleading picture a stale highlight gives, arrived at the other way.
    const dimmed = routes.some((route) => route.routeId === highlightedRouteId);
    source.setData({
      type: "FeatureCollection",
      features: routes.map((route, index) => {
        const on = route.routeId === highlightedRouteId;
        return {
          type: "Feature" as const,
          properties: {
            color: routeColor(index, scheme),
            width: on ? 6 : 3.5,
            opacity: dimmed && !on ? 0.25 : 0.9,
          },
          geometry: { type: "LineString" as const, coordinates: pathOf(route, venue, leg) },
        };
      }),
    });
  }, [routes, venue, leg, highlightedRouteId, ready, scheme]);

  // Markers. Rebuilt wholesale: they are few, and a solution changing is a new answer rather than
  // an edit to the old one, so there is no drag or hover state worth preserving across it.
  useEffect(() => {
    const instance = map.current;
    if (!instance || !ready) return;

    markers.current.forEach((m) => m.remove());
    markers.current = [];

    if (venue) {
      markers.current.push(
        new Marker({ element: venuePin(scheme, `Destination — ${venue.address}`) })
          .setLngLat([venue.lng, venue.lat])
          .addTo(instance),
      );
    }

    routes.forEach((route, index) => {
      const color = routeColor(index, scheme);
      if (route.home) {
        markers.current.push(
          new Marker({ element: homePin(scheme, color, `${route.driverName} (home)`) })
            .setLngLat([route.home.lng, route.home.lat])
            .addTo(instance),
        );
      }
      route.stops.forEach((stop) => {
        markers.current.push(
          new Marker({
            element: stopPin(scheme, color, `${stop.label} — ${route.driverName}`, stop.number),
          })
            .setLngLat([stop.lng, stop.lat])
            .addTo(instance),
        );
      });
    });
  }, [routes, venue, leg, ready, scheme]);

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
    <MapFrame
      container={container}
      label="Each car's route, with stops numbered in pickup order."
      overlay={overlay}
      caption={
        failed
          ? "The map could not load. Every car and stop is listed beside it in order."
          : captionFor(routes)
      }
    />
  );
}
