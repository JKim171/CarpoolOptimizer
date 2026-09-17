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
 * Tiles are OpenFreeMap. MapLibre is a renderer, not a tile source (docs/design.md 7.5), so a
 * source had to be chosen: OpenFreeMap needs no key and no account, which keeps the "no credential
 * ever reaches the browser" property the rest of this design depends on. MapTiler and Stadia both
 * want a key that would either ship in the bundle or need a second proxy.
 */

import { Map as MapLibreMap, Marker, NavigationControl, setWorkerUrl } from "maplibre-gl";
import { useEffect, useRef, useState } from "react";

import "maplibre-gl/dist/maplibre-gl.css";

const STYLE = "https://tiles.openfreemap.org/styles/liberty";

/**
 * Point MapLibre at the worker copied into `public/` by `scripts/copy-maplibre-worker.mjs`.
 *
 * Without this the worker request resolves through `import.meta.url` to something Turbopack never
 * emitted, Next answers with its HTML 404 page, and the browser rejects it for its MIME type. No
 * tile is then decoded, while the style and sprites -- fetched on the main thread -- load fine, so
 * the map is a correctly sized blank rectangle and MapLibre reports no error. That failure took a
 * while to find; see the script for why 5.x is not the way out.
 */
setWorkerUrl("/maplibre/maplibre-gl-worker.mjs");

export type Point = { lat: number; lng: number };

export function DestinationMap({
  point,
  onMove,
  className,
}: {
  point: Point | null;
  onMove: (point: Point) => void;
  className?: string;
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

  useEffect(() => {
    if (!container.current || map.current) return;

    const instance = new MapLibreMap({
      container: container.current,
      style: STYLE,
      center: point ? [point.lng, point.lat] : [-83.743, 42.2808],
      zoom: point ? 15 : 11,
      // Attribution is not decoration: OpenFreeMap serves OpenStreetMap data and the licence
      // requires crediting it.
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

  useEffect(() => {
    const instance = map.current;
    if (!instance || !point) return;

    if (!marker.current) {
      marker.current = new Marker({ draggable: true, color: "#1d4ed8" })
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
  }, [point]);

  return (
    <div className={className}>
      <div
        ref={container}
        className="h-64 w-full overflow-hidden rounded-md border border-line bg-surface-sunken"
        role="application"
        aria-label="Destination location. Drag the marker to correct it."
      />
      <p className="mt-1 text-xs text-ink-muted">
        {failed
          ? "The map could not load. You can still enter an address and coordinates below."
          : point
            ? "Drag the pin to the exact meeting point — a parking entrance, not the building centre."
            : "Choose an address to place the pin."}
      </p>
    </div>
  );
}
