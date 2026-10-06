/**
 * Which theme the browser is actually showing, as a value React can read.
 *
 * Everything else in this app answers `prefers-color-scheme` in CSS, which is the right tool and
 * needs no JavaScript. The map cannot: MapLibre paints into a canvas from a style fetched over the
 * network, and the marker elements are built with inline `style` strings rather than classes. So
 * the basemap URL, the eight route colours and the pin rings all have to be *chosen*, in JS, at the
 * moment the map is built -- and re-chosen when the preference changes under a running page.
 *
 * Exposed through `useSyncExternalStore` for the same reason `lib/api/tokens.ts` is: the value does
 * not exist during server rendering, and bridging that with state set in an effect produces a
 * render with the wrong answer in it. The server snapshot is `light`, so SSR matches what a browser
 * with no preference gets; a dark-mode client corrects it on hydration without a flash, because the
 * map has not been built yet at that point either way.
 */

import { useSyncExternalStore } from "react";

export type ColorScheme = "light" | "dark";

const QUERY = "(prefers-color-scheme: dark)";

/** No `window` while server-rendering, and no `matchMedia` in very old browsers or some test DOMs. */
const query = (): MediaQueryList | null => {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return null;
  return window.matchMedia(QUERY);
};

export function subscribeToColorScheme(onChange: () => void): () => void {
  const list = query();
  if (!list) return () => {};
  list.addEventListener("change", onChange);
  return () => list.removeEventListener("change", onChange);
}

export function colorSchemeSnapshot(): ColorScheme {
  return query()?.matches ? "dark" : "light";
}

export function colorSchemeServerSnapshot(): ColorScheme {
  return "light";
}

/**
 * The hook every call site actually wants. Kept in this file rather than its own so that "what
 * theme is it" is one import and one concept, the way `tokens.ts` holds both the storage and the
 * snapshot functions the home screen subscribes to.
 */
export function useColorScheme(): ColorScheme {
  return useSyncExternalStore(
    subscribeToColorScheme,
    colorSchemeSnapshot,
    colorSchemeServerSnapshot,
  );
}
