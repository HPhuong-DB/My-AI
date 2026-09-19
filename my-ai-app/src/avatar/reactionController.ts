import type { ReactionPlan } from './reaction.ts';

export interface ReactionPlayer { play: (plan: ReactionPlan) => void; reset: () => void; }
interface Clock { now: () => number; schedule: (callback: () => void, ms: number) => unknown; cancel: (timer: unknown) => void; }

/** One reaction at a time. Deadlines also apply while the model is loading. */
export function createReactionController(clock: Clock) {
  let player: ReactionPlayer | null = null;
  let pending: { plan: ReactionPlan; until: number } | null = null;
  let timer: unknown;
  let revision = 0;
  let disposed = false;
  let lastMotion = '';
  let lastMotionAt = -Infinity;
  const reset = () => {
    revision++;
    clock.cancel(timer);
    timer = undefined;
    pending = null;
    player?.reset();
  };
  const apply = () => {
    if (!player || !pending || pending.until <= clock.now()) return;
    const remaining = pending.until - clock.now();
    const plan = { ...pending.plan, holdMs: remaining };
    if (plan.motion && plan.motion === lastMotion && clock.now() - lastMotionAt < 12_000) plan.motion = '';
    if (plan.motion) { lastMotion = plan.motion; lastMotionAt = clock.now(); }
    player.play(plan);
  };
  return {
    attach(next: ReactionPlayer) {
      if (disposed) return;
      player?.reset();
      player = next;
      player.reset();
      apply();
    },
    play(plan: ReactionPlan) {
      if (disposed) return;
      reset();
      if (!plan.holdMs) return;
      pending = { plan, until: clock.now() + plan.holdMs };
      const current = revision;
      timer = clock.schedule(() => { if (current === revision) reset(); }, plan.holdMs);
      apply();
    },
    reset,
    destroy() { reset(); player = null; disposed = true; },
  };
}
