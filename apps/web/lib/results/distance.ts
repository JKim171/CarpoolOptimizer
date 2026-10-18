/** Metres to the nearest tenth of a mile. The audience is a US campus club (docs/design.md 2). */
export function formatDistance(metres: number): string {
  return `${(metres / 1609.344).toFixed(1)} mi`;
}
