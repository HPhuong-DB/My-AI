export interface Availability { visible: boolean; busy: boolean; typing: boolean; reading: boolean; local_hour: number; }
export function canPresentProactive(state: Availability, expiresAt: unknown, now = Date.now()): boolean {
  if (!state.visible || state.busy || state.typing || state.reading || state.local_hour < 8 || state.local_hour >= 22) return false;
  if (typeof expiresAt !== 'string') return false;
  const expires = Date.parse(expiresAt);
  return Number.isFinite(expires) && expires > now && expires - now <= 35_000;
}
