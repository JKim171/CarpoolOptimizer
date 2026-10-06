"use client";

/**
 * The destination pin, with drag-to-adjust.
 *
 * Small feature, disproportionate payoff: "Nielsen Tennis Stadium" geocodes to a building centroid,
 * but the meeting point is a particular parking-lot entrance. Dragging writes a corrected
 * coordinate back, and that correction silently improves every ETA the system will ever produce for
 * that venue (docs/design.md 7.2).
 *
 * A dragged pin is also the one coordinate the design keeps **permanently**: it came from a human
 * action rather than the provider, so it is not subject to a geocoder's storage terms and is stored
 * with `geocode_source = 'user'` (docs/design.md 5.2).
 *
 * Tile source and worker setup are shared -- see `components/map/basemap.ts`.
 */

import { Map as MapLibreMap, Marker, NavigationControl } from "maplibre-gl";
import { useEffect, useRef, useState } from "react";

import { FALLBACK_CENTER, styleFor } from "@/components/map/basemap";
import { MapFrame } from "@/components/map/MapFrame";
import { venuePin } from "@/components/map/markers";
import { useColorScheme } from "@/lib/colorScheme";

import "maplibre-gl/dist/maplibre-gl.css";

export type Point = { lat: number; lng: number };

export function DestinationMap({
  point,
  onMove,
}: {
  point: Point | null;
  onMove: (point: Point) => void;
}) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<MapLibreMap | null>(null);
  const marker = useRef<Marker | null>(null);
  // `onMove` is a new function on every render; the drag handler is bound once, so it reads the
  // latest through a ref rather than forcing the map to be torn down and rebuilt each time.
  // Assigned in an effect, not during render -- a ref written while rendering is not guaranteed to
  // survive a render React discards.
  const handler = useRef(onMove);
  useEffect(() => {
    handler.current = onMove;
  }, [onMove]);

  const [failed, setFailed] = useState(false);
  const scheme = useColorScheme();
  /** Which basemap the live instance is showing, so the effect below is a no-op at mount. */
  const applied = useRef(scheme);

  useEffect(() => {
    if (!container.current || map.current) return;

    const instance = new MapLibreMap({
      container: container.current,
      style: styleFor(applied.current),
      center: point ? [point.lng, point.lat] : FALLBACK_CENTER,
      zoom: point ? 15 : 11,
      attributionControl: { compact: true },
    });
    instance.addControl(new NavigationControl({ showCompass: false }), "top-right");

    // If tiles fail the list view must stay usable -- the map is never the only path to an answer
    // (docs/design.md 7.5). The form below still takes a typed address and coordinates.
    instance.on("error", (event) => {
      if (event.error?.message?.includes("style")) setFailed(true);
    });

    map.current = instance;
    return () => {
      instance.remove();
      map.current = null;
      marker.current = null;
    };
    // Deliberately built once. `point` is read for the initial view only; later changes move the
    // marker below rather than recreating the map, which would fight the user mid-drag.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /**
   * Swap the basemap when the system theme changes under a running page.
   *
   * The marker is a DOM overlay and survives `setStyle`, but it carries the theme's colours in an
   * inline `style`, so it is dropped here and rebuilt by the effect below -- which is guarded on
   * `marker.current` being null, and now gets that. **Declared before that effect on purpose:**
   * effects run in source order, so the other way round the rebuild would run first, find a marker
   * still there, and leave the old colour on screen until the point next moved.
   */
  useEffect(() => {
    const instance = map.current;
    if (!instance || applied.current === scheme) return;
    applied.current = scheme;
    marker.current?.remove();
    marker.current = null;
    instance.setStyle(styleFor(scheme));
  }, [scheme]);

  useEffect(() => {
    const instance = map.current;
    if (!instance || !point) return;

    if (!marker.current) {
      // The same red square the destination gets on both event-page maps. This was MapLibre's
      // default teardrop in `#1d4ed8`, which is the *first car's* colour -- so the venue was drawn
      // in the one palette `routeColor` excludes precisely so that it never could be.
      marker.current = new Marker({
        draggable: true,
        element: venuePin(scheme, "Destination — drag to the exact meeting point"),
      })
        .setLngLat([point.lng, point.lat])
        .addTo(instance);
      marker.current.on("dragend", () => {
        const moved = marker.current!.getLngLat();
        handler.current({ lat: moved.lat, lng: moved.lng });
      });
    } else {
      marker.current.setLngLat([point.lng, point.lat]);
    }
    instance.easeTo({ center: [point.lng, point.lat], zoom: Math.max(instance.getZoom(), 15) });
  }, [point, scheme]);

  return (
    <MapFrame
      container={container}
      label="Destination location. Drag the marker to correct it."
      caption={
        failed
          ? "The map could not load. You can still enter an address and coordinates in the panel."
          : point
            ? "Drag the pin to the exact meeting point — a parking entrance, not the building centre."
            : "Choose an address to place the pin."
      }
    />
  );
}
