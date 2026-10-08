/**
 * Which theme the app is showing, and which one the reader asked for.
 *
 * Two different questions, and both live here because every call site wants one of them and keeping
 * them apart produced the usual bug: a component that knows the *preference* is `system` still has
 * to paint something, and a component that knows the *scheme* is `dark` cannot tell you whether to
 * tick "Dark" or "Auto" in the control.
 *
 *  - `ThemePreference` -- `system` | `light` | `dark`. What the reader chose, kept in localStorage.
 *  - `ColorScheme` -- `light` | `dark`. What is actually on screen, after resolving `system`
 *    against `prefers-color-scheme`.
 *
 * **Most of the app needs neither.** The palette is CSS custom properties answered by a media query
 * and a `data-theme` attribute (see `app/globals.css`), so a component gets dark mode by naming
 * `text-ink` and nothing else. The maps are why this file exists: MapLibre paints into a canvas
 * from a style fetched over the network, and the marker elements are built with inline `style`
 * strings rather than classes, so the basemap URL, the eight route colours and the pin rings have
 * to be *chosen*, in JS, at the moment the map is built -- and re-chosen when the answer changes
 * under a running page.
 *
 * Exposed through `useSyncExternalStore` for the same reason `lib/api/tokens.ts` is: the value does
 * not exist during server rendering, and bridging that with state set in an effect produces a
 * render with the wrong answer in it. The server snapshot is `light`, so SSR matches what a browser
 * with no preference gets; a client corrects it on hydration without a flash, because the map has
 * not been built yet at that point either way -- and because the attribute that drives the CSS was
 * already written by the pre-paint script in `app/layout.tsx`, which runs before React.
 */

import { useSyncExternalStore } from "react";

export type ColorScheme = "light" | "dark";
export type ThemePreference = "system" | ColorScheme;

const QUERY = "(prefers-color-scheme: dark)";

/** Not under the `carpool.organizer.` prefix: `knownEventIds` treats every key there as an event. */
const KEY = "carpool.theme";

/** No `window` while server-rendering, and no `matchMedia` in very old browsers or some test DOMs. */
const query = (): MediaQueryList | null => {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return null;
  return window.matchMedia(QUERY);
};

/** Server-render passes through here too, where there is no `window`. */
const storage = (): Storage | null => {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage;
  } catch {
    // Safari in private mode, and any browser with site data blocked, throws on access rather than
    // returning null. The app stays usable: the theme follows the OS and the control still works
    // for this page view, it just will not be remembered.
    return null;
  }
};

const isPreference = (value: string | null): value is ThemePreference =>
  value === "system" || value === "light" || value === "dark";

/**
 * The cached preference, and the listeners watching it.
 *
 * `useSyncExternalStore` calls its snapshot on every render, so the snapshot cannot hit
 * localStorage every time. Same shape as the known-events list in `tokens.ts`: cache, invalidate
 * on write, notify.
 */
let cached: ThemePreference | null = null;
const listeners = new Set<() => void>();

function readStored(): ThemePreference {
  const raw = storage()?.getItem(KEY) ?? null;
  // Anything else -- a value from an older build, or a hand-edited one -- means "no answer", and
  // following the OS is the right answer to that.
  return isPreference(raw) ? raw : "system";
}

/**
 * Put the preference where CSS can see it.
 *
 * `system` removes the attribute rather than writing it, which is what lets the media block in
 * `globals.css` apply on its own. Writing `data-theme="system"` would match neither rule and pin
 * the app to light.
 *
 * Exported because the pre-paint script in `app/layout.tsx` does this same job, in the same way,
 * before any of this module is loaded -- the two must agree, so the shape is written down once
 * here and once there, and the comment in each points at the other.
 */
export function applyPreference(preference: ThemePreference): void {
  if (typeof document === "undefined") return;
  const root = document.documentElement;
  if (preference === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", preference);
}

export function setThemePreference(preference: ThemePreference): void {
  storage()?.setItem(KEY, preference);
  applyPreference(preference);
  cached = preference;
  for (const listener of listeners) listener();
}

export function themePreferenceSnapshot(): ThemePreference {
  cached ??= readStored();
  return cached;
}

export function themePreferenceServerSnapshot(): ThemePreference {
  return "system";
}

/**
 * One subscription for both questions.
 *
 * Three things can change the answer: the reader picks a theme here, the OS preference flips while
 * the page is open, or another tab picks a theme. The third also has to re-apply the attribute --
 * this tab's CSS will not update itself from another tab's write.
 */
export function subscribeToColorScheme(onChange: () => void): () => void {
  listeners.add(onChange);

  const list = query();
  const onQueryChange = () => onChange();
  list?.addEventListener("change", onQueryChange);

  const onStorage = (event: StorageEvent) => {
    if (event.key !== null && event.key !== KEY) return;
    cached = null;
    applyPreference(themePreferenceSnapshot());
    onChange();
  };
  // `storage` fires only in *other* tabs, which is exactly the case this listener is for. Writes in
  // this tab notify through `setThemePreference` above.
  if (typeof window !== "undefined") window.addEventListener("storage", onStorage);

  return () => {
    listeners.delete(onChange);
    list?.removeEventListener("change", onQueryChange);
    if (typeof window !== "undefined") window.removeEventListener("storage", onStorage);
  };
}

export function colorSchemeSnapshot(): ColorScheme {
  const preference = themePreferenceSnapshot();
  if (preference !== "system") return preference;
  return query()?.matches ? "dark" : "light";
}

export function colorSchemeServerSnapshot(): ColorScheme {
  return "light";
}

/**
 * The hook most call sites want: what is on screen right now.
 *
 * Kept in this file rather than its own so that "what theme is it" is one import and one concept,
 * the way `tokens.ts` holds both the storage and the snapshot functions the home screen subscribes
 * to.
 */
export function useColorScheme(): ColorScheme {
  return useSyncExternalStore(
    subscribeToColorScheme,
    colorSchemeSnapshot,
    colorSchemeServerSnapshot,
  );
}

/** The preference, and a setter, for the control that changes it. */
export function useThemePreference(): [ThemePreference, (next: ThemePreference) => void] {
  const preference = useSyncExternalStore(
    subscribeToColorScheme,
    themePreferenceSnapshot,
    themePreferenceServerSnapshot,
  );
  // `setThemePreference` is a module-level function, so it is already referentially stable --
  // wrapping it in `useCallback` would buy nothing and claim otherwise.
  return [preference, setThemePreference];
}

/**
 * The same answer, but never the server's placeholder -- for imperative code.
 *
 * `useColorScheme` has to return `light` on the hydration render whatever the browser is showing,
 * because that render must reproduce the server's HTML exactly. For anything *rendered* that is
 * correct and self-correcting: React re-renders with the real value immediately afterwards.
 *
 * For the maps it is not, because they do not render their contents -- they build a MapLibre
 * instance in an effect, and anything captured in a ref during that first render is captured for
 * good. Seeding the basemap from it meant **every page load on a dark machine fetched `positron`
 * first and then swapped to `dark`**: a wasted style request and a visible flash of a light map on
 * a dark page, which is precisely the thing the dark basemap exists to avoid.
 *
 * So: subscribe through the hook, to re-render when the answer actually changes, and report the
 * live value. Use this wherever the answer feeds an effect or a ref. Use `useColorScheme` wherever
 * it feeds JSX -- `RouteCard` sets an inline colour from it, and reading the live value there would
 * be a genuine hydration mismatch.
 */
export function useLiveColorScheme(): ColorScheme {
  useColorScheme();
  return colorSchemeSnapshot();
}
