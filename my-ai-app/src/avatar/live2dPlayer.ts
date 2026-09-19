import type { Cubism4InternalModel, Live2DModel } from 'pixi-live2d-display/cubism4';
import type { ReactionPlan } from './reaction.ts';

/** Cubism adapter; no network work beyond the model's existing asset loader. */
export function createLive2DPlayer(model: Live2DModel, now: () => number, reducedMotion: () => boolean) {
  const internal = model.internalModel as Cubism4InternalModel;
  const manager = internal.motionManager;
  manager.expressionManager?.defaultExpression.setFadeInTime(0.35);
  const core = internal.coreModel;
  const base = Array.from({ length: core.getParameterCount() }, (_, index) => core.getParameterValueByIndex(index));
  let returnPose: { started: number; values: number[] } | undefined;
  let revision = 0;
  let disposed = false;
  const oneShot = (_group: string, _index: number, motion: { setIsLoop: (value: boolean) => void }) => motion.setIsLoop(false);
  manager.on('motionLoaded', oneShot);
  Object.values(manager.motionGroups).forEach((motions) => motions?.forEach((motion) => motion?.setIsLoop(false)));
  const restorePose = () => {
    if (!returnPose) return;
    const progress = Math.min(1, (now() - returnPose.started) / 350);
    const weight = progress * progress * (3 - 2 * progress);
    base.forEach((value, index) => core.setParameterValueByIndex(index, returnPose!.values[index] + (value - returnPose!.values[index]) * weight));
    if (progress === 1) returnPose = undefined;
  };
  internal.on('beforeMotionUpdate', restorePose);
  const reset = () => {
    if (disposed) return;
    revision++;
    manager.stopAllMotions();
    const expressions = manager.expressionManager;
    if (expressions) {
      expressions.reserveExpressionIndex = -1;
      expressions.currentExpression = expressions.defaultExpression;
      expressions.resetExpression(); // expression('') is NOT a reset in this library.
    }
    returnPose = { started: now(), values: base.map((_, index) => core.getParameterValueByIndex(index)) };
  };
  return {
    reset,
    play(plan: ReactionPlan) {
      if (disposed) return;
      const current = ++revision;
      void (async () => {
        if (plan.motion && !reducedMotion()) await model.motion(plan.motion, 0, 3);
        // Motion start may reset expressions. Set the expression after it starts.
        if (disposed || revision !== current) return;
        if (plan.expression) await model.expression(plan.expression);
      })().catch((cause) => {
        if (!disposed && revision === current) { reset(); console.warn('Không thể phát phản ứng Live2D:', cause); }
      });
    },
    destroy() {
      reset(); disposed = true;
      manager.off('motionLoaded', oneShot);
      internal.off('beforeMotionUpdate', restorePose);
    },
  };
}
