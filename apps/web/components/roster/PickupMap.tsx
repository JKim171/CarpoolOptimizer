"use client";

/**
 * Every pickup on one map, linked to the roster table beside it.
 *
 * "The list decides, the map verifies" (a standing decision): the table is where a roster is
 * entered and edited, and this exists to make a wrong coordinate *visible*. A geocoder that puts
 * someone in the next county produces a plausible-looking row and an absurd pin, and the pin is the
 * only one of the two a human notices.
 *
 * Highlighting is linked both ways so the verification actually works -- a pin in the wrong place
 * is useless if you cannot tell whose it is. Hovering a row raises its pin; hovering a pin names
 * the row.
 *
 * Dragging a pin writes the correction back. That coordinate is then stored with
 * `geocode_source = 'user'`, the one provenance the design keeps permanently, because it came from
 * a human rather than the provider (docs/design.md 5.2).
 *
 * **The map also takes a pickup that the geocoder could not produce.** While the add-person form
 * is open and still has no coordinates, a click on the map places its pin -- the `draft`, drawn
 * with a dashed halo because it is not on the roster yet. That path is not a nicety: autocomplete
 * returns nothing for plenty of ordinary addresses, and `AddParticipantForm` has no other way to
 * obtain a coordinate, so without it a coordinator whose street the provider has never heard of
 * simply cannot add that person. As on the destination map, a click only ever *creates* the pin;
 * once it exists it is moved by dragging, so reading the map cannot relocate someone's house.
 */

import { Map as MapLibreMap, Marker, NavigationControl } from "maplibre-gl";
import { useEffect, useRef, useState, type ReactNode } from "react";

import { FALLBACK_CENTER, styleFor } from "@/components/map/basemap";
import { MapFrame } from "@/components/map/MapFrame";
import { draftPin, personPin, venuePin } from "@/components/map/markers";
import type { LocatedParticipant } from "@/lib/api/participants";
import { useLiveColorScheme, type ColorScheme } from "@/lib/colorScheme";

import "maplibre-gl/dist/maplibre-gl.css";

export type Destination = { address: string; lat: number; lng: number };
export type Point = { lat: number; lng: number };

/**
 * Marker colours carry meaning: drivers are the scarce resource a coordinator is counting, and the
 * destination is not a person. Shapes carry it too -- see `components/map/markers.ts`, which owns
 * the vocabulary so that the three maps in this app cannot disagree about it.
 *
 * Two sets, for the two basemaps, on the same reasoning as `lib/results/colors.ts`: these sit on
 * tiles rather than on the page. The driver blue tracks the first car's colour in each palette, so
 * a driver on the roster map and car one on the results map are recognisably the same blue.
 */
const COLOR: Record<ColorScheme, { driver: string; passenger: string }> = {
  light: { driver: "#1d4ed8", passenger: "#63636d" },
  dark: { driver: "#60a5fa", passenger: "#9ca3af" },
};

export function PickupMap({
  participants,
  destination,
  highlightedId,
  onHighlight,
  onMove,
  overlay,
  draft,
  onDraft,
  placing,
}: {
  participants: LocatedParticipant[];
  destination: Destination | null;
  highlightedId: string | null;
  onHighlight: (id: string | null) => void;
  onMove: (id: string, point: { lat: number; lng: number }) => void;
  /** Controls drawn over the map -- the canvas's mode switch. */
  overlay?: ReactNode;
  /** The pickup the add-person form is holding, placed here rather than by the geocoder. */
  draft: Point | null;
  onDraft: (point: Point) => void;
  /** True while that form is the open tab, which is the only time a click may place a pin. */
  placing: boolean;
}) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<MapLibreMap | null>(null);
  const markers = useRef(new Map<string, Marker>());
  const destinationMarker = useRef<Marker | null>(null);
  const draftMarker = useRef<Marker | null>(null);
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);
  const scheme = useLiveColorScheme();
  /** Which basemap the live instance is actually showing, so the effect below is a no-op at mount. */
  const applied = useRef(scheme);

  // Callbacks are new functions every render while marker handlers are bound once, so they are read
  // through refs. Assigned in an effect -- a ref written during render is not guaranteed to survive
  // a render React discards.
  const highlightHandler = useRef(onHighlight);
  const moveHandler = useRef(onMove);
  const draftHandler = useRef(onDraft);
  // `placing` is read by the click handler, which is bound once with the map, so it has to be a
  // ref rather than a closed-over prop -- otherwise the map keeps forever whichever tab was open
  // when it mounted.
  const placingNow = useRef(placing);
  useEffect(() => {
    highlightHandler.current = onHighlight;
    moveHandler.current = onMove;
    draftHandler.current = onDraft;
    placingNow.current = placing;
  }, [onHighlight, onMove, onDraft, placing]);

  useEffect(() => {
    if (!container.current || map.current) return;
    // Captured for the cleanup closure: reading `markers.current` there would read whatever the ref
    // holds at unmount rather than the registry this effect populated.
    const registry = markers.current;

    const instance = new MapLibreMap({
      container: container.current,
      style: styleFor(applied.current),
      center: destination ? [destination.lng, destination.lat] : FALLBACK_CENTER,
      zoom: 11,
      attributionControl: { compact: true },
    });
    instance.addControl(new NavigationControl({ showCompass: false }), "top-right");
    // `style.load`, not `load`: it fires for the first style and for every one `setStyle` swaps in,
    // so `ready` tracks the live style rather than only the first.
    instance.on("style.load", () => setReady(true));
    instance.on("error", (event) => {
      if (event.error?.message?.includes("style")) setFailed(true);
    });

    instance.on("click", (event) => {
      if (!placingNow.current || draftMarker.current) return;
      draftHandler.current({ lat: event.lngLat.lat, lng: event.lngLat.lng });
    });

    map.current = instance;
    return () => {
      instance.remove();
      map.current = null;
      registry.clear();
      destinationMarker.current = null;
      draftMarker.current = null;
      setReady(false);
    };
    // Built once; later prop changes move markers rather than rebuilding the map, which would fight
    // the user mid-drag.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /**
   * Swap the basemap when the system theme changes under a running page.
   *
   * Markers are DOM overlays, so `setStyle` does not touch them -- but they are built with the
   * theme's colours baked into an inline `style`, and the reconcile effect below deliberately
   * leaves an existing marker alone. Dropping them here is what makes that effect rebuild them in
   * the new palette; it is the one case where "the roster did not change" is not a reason to keep
   * the pin that is already there.
   */
  useEffect(() => {
    const instance = map.current;
    if (!instance || applied.current === scheme) return;
    applied.current = scheme;
    markers.current.forEach((marker) => marker.remove());
    markers.current.clear();
    destinationMarker.current?.remove();
    destinationMarker.current = null;
    draftMarker.current?.remove();
    draftMarker.current = null;
    setReady(false);
    instance.setStyle(styleFor(scheme));
  }, [scheme]);

  // Destination pin, kept separate from the roster so it is not re-created on every roster change.
  useEffect(() => {
    const instance = map.current;
    if (!instance || !ready || !destination) return;
    if (!destinationMarker.current) {
      destinationMarker.current = new Marker({
        element: venuePin(scheme, `Destination — ${destination.address}`, "carpool-pin"),
      })
        .setLngLat([destination.lng, destination.lat])
        .addTo(instance);
    } else {
      destinationMarker.current.setLngLat([destination.lng, destination.lat]);
    }
  }, [destination, ready, scheme]);

  /**
   * The pin being placed by hand, which belongs to no one yet.
   *
   * Kept out of the roster reconcile above because it is keyed by nothing -- there is at most one,
   * it has no participant id, and it must not be swept by the "remove the gone" pass. It is also
   * deliberately left out of the fit below: the organizer placed it by clicking a spot they were
   * already looking at, and refitting the view out from under that click is the one thing that
   * would make placing a second pin harder than the first.
   */
  useEffect(() => {
    const instance = map.current;
    if (!instance || !ready) return;

    if (!draft) {
      draftMarker.current?.remove();
      draftMarker.current = null;
      return;
    }

    if (draftMarker.current) {
      draftMarker.current.setLngLat([draft.lng, draft.lat]);
      return;
    }

    const marker = new Marker({
      element: draftPin(scheme, COLOR[scheme].passenger, "New pickup — drag to adjust"),
      draggable: true,
    })
      .setLngLat([draft.lng, draft.lat])
      .addTo(instance);
    marker.on("dragend", () => {
      const moved = marker.getLngLat();
      draftHandler.current({ lat: moved.lat, lng: moved.lng });
    });
    draftMarker.current = marker;
  }, [draft, ready, scheme]);

  // Reconcile markers against the roster: add new people, move changed ones, remove the gone.
  useEffect(() => {
    const instance = map.current;
    if (!instance || !ready) return;

    const seen = new Set<string>();

    for (const person of participants) {
      seen.add(person.id);
      const existing = markers.current.get(person.id);
      const lngLat: [number, number] = [person.pickup.lng, person.pickup.lat];

      if (existing) {
        existing.setLngLat(lngLat);
        continue;
      }

      const element = personPin(
        scheme,
        person.role === "driver" ? COLOR[scheme].driver : COLOR[scheme].passenger,
        `${person.display_name} — ${person.pickup.address}`,
        "carpool-pin",
      );
      element.addEventListener("mouseenter", () => highlightHandler.current(person.id));
      element.addEventListener("mouseleave", () => highlightHandler.current(null));

      const marker = new Marker({ element, draggable: true }).setLngLat(lngLat).addTo(instance);
      marker.on("dragstart", () => highlightHandler.current(person.id));
      marker.on("dragend", () => {
        const moved = marker.getLngLat();
        moveHandler.current(person.id, { lat: moved.lat, lng: moved.lng });
      });
      markers.current.set(person.id, marker);
    }

    for (const [id, marker] of markers.current) {
      if (!seen.has(id)) {
        marker.remove();
        markers.current.delete(id);
      }
    }
  }, [participants, ready, scheme]);

  // Highlight is a style change on an existing element, not a marker rebuild -- rebuilding would
  // drop a drag in progress and make hovering the table feel like the map was flickering.
  useEffect(() => {
    for (const [id, marker] of markers.current) {
      const element = marker.getElement();
      const on = id === highlightedId;
      element.style.transform = `${element.style.transform.replace(/ scale\([^)]*\)/, "")}${
        on ? " scale(1.6)" : ""
      }`;
      element.style.zIndex = on ? "10" : "";
    }
  }, [highlightedId, participants]);

  // Fit the view to everything once there is something to fit. Only while the user is not
  // highlighting: refitting mid-inspection moves the thing being looked at.
  useEffect(() => {
    const instance = map.current;
    if (!instance || !ready || highlightedId) return;
    const points: [number, number][] = participants.map((p) => [p.pickup.lng, p.pickup.lat]);
    if (destination) points.push([destination.lng, destination.lat]);
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
    // `highlightedId` is read to suppress refitting, deliberately not to trigger one.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [participants, destination, ready]);

  return (
    // This map used to be deliberately *not* full-bleed: hovering a table row highlights its pin
    // and vice versa, and that pairing only works while both are on screen, so a map that filled
    // the window would have pushed the table it is paired with off the bottom. In the shell the
    // table is in the rail and the map is the canvas, so they are always both on screen and the
    // reason to keep it small is gone.
    <MapFrame
      container={container}
      label="Pickup locations. Drag a pin to correct someone's address."
      overlay={overlay}
      caption={
        failed
          ? "The map could not load. The roster table is still authoritative — every address is listed there."
          : // While a pickup is being placed the caption says so and says nothing else: it is the
            // one moment the map is an input rather than a check, and the instruction for that is
            // worth more than the standing advice about hovering rows.
            draft
            ? "Drag the new pin to the exact pickup point, then add the person."
            : placing
              ? "Click the map to place this person's pickup, or pick an address in the panel."
              : participants.length === 0
                ? "Pickups appear here as you add people."
                : "Drag a pin to correct a pickup point. Hover a row to find someone."
      }
    />
  );
}
