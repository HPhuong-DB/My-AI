import { useEffect, useImperativeHandle, useRef, useState } from 'react';
import type { Ref } from 'react';
import * as PIXI from 'pixi.js';
import { Live2DModel, MotionPreloadStrategy } from 'pixi-live2d-display/cubism4';
import { createReactionController } from '../avatar/reactionController';
import { createLive2DPlayer } from '../avatar/live2dPlayer';
import type { AvatarHandle } from '../types';

(window as unknown as { PIXI: typeof PIXI }).PIXI = PIXI;
(PIXI.Container.prototype as unknown as Record<string, unknown>).isInteractive = function (this: PIXI.Container) { return this.interactive; };

export default function AvatarStage({ ref }: { ref?: Ref<AvatarHandle> }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const director = useRef<ReturnType<typeof createReactionController> | null>(null);
  const [error, setError] = useState('');
  useImperativeHandle(ref, () => ({
    play(plan) { if (!document.hidden) director.current?.play(plan); },
    reset() { director.current?.reset(); },
  }), []);
  useEffect(() => {
    if (!canvas.current) return;
    let disposed = false;
    let player: ReturnType<typeof createLive2DPlayer> | undefined;
    const reactions = createReactionController({
      now: () => performance.now(),
      schedule: (callback, ms) => window.setTimeout(callback, ms),
      cancel: (timer) => window.clearTimeout(timer as number | undefined),
    });
    director.current = reactions;
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
    let clearGaze = () => {};
    let releaseGaze = () => {};
    const reset = () => { reactions.reset(); clearGaze(); };
    const onVisibility = () => { if (document.hidden) reset(); };
    document.addEventListener('visibilitychange', onVisibility);
    reduced.addEventListener('change', reset);
    const app = new PIXI.Application({ view: canvas.current, autoStart: true, backgroundAlpha: 0, width: 760, height: 480 });
    let fitModel: (() => void) | undefined;
    const resize = () => {
      const rect = canvas.current?.parentElement?.getBoundingClientRect();
      if (rect) { app.renderer.resize(Math.max(1, rect.width), Math.max(1, rect.height)); fitModel?.(); }
    };
    const observer = new ResizeObserver(resize);
    if (canvas.current.parentElement) observer.observe(canvas.current.parentElement);
    resize();
    void Live2DModel.from('/live2d/huohuo/huohuo.model3.json', { autoInteract: false, motionPreload: MotionPreloadStrategy.ALL }).then((model) => {
      if (disposed) { model.destroy(); return; }
      app.stage.addChild(model as unknown as PIXI.Container);
      const baseWidth = model.width, baseHeight = model.height;
      model.anchor.set(0.5, 0.5);
      fitModel = () => model.scale.set(Math.min(app.renderer.width * .94 / baseWidth, app.renderer.height * .88 / baseHeight));
      fitModel();
      model.interactive = false;
      // Use Cubism's smoothed focus, with a small range so expressions stay natural.
      const stage = canvas.current?.parentElement;
      const focus = model.internalModel.focusController;
      const center = () => focus.focus(0, 0, reduced.matches || document.hidden);
      const followPointer = (event: PointerEvent) => {
        if (!stage || reduced.matches || document.hidden || event.pointerType === 'touch') { center(); return; }
        const rect = stage.getBoundingClientRect();
        if (!rect.width || !rect.height) return;
        const clamp = (value: number) => Math.max(-1, Math.min(1, value));
        const x = clamp((event.clientX - rect.left - rect.width / 2) / (rect.width / 2));
        const y = clamp((rect.top + rect.height * .4 - event.clientY) / (rect.height / 2));
        focus.focus(x * .3, y * .22);
      };
      clearGaze = center;
      stage?.addEventListener('pointermove', followPointer);
      stage?.addEventListener('pointerleave', center);
      stage?.addEventListener('pointercancel', center);
      window.addEventListener('blur', center);
      releaseGaze = () => {
        stage?.removeEventListener('pointermove', followPointer);
        stage?.removeEventListener('pointerleave', center);
        stage?.removeEventListener('pointercancel', center);
        window.removeEventListener('blur', center);
        focus.focus(0, 0, true);
      };
      player = createLive2DPlayer(model, () => performance.now(), () => reduced.matches);
      reactions.attach(player);
      app.ticker.add(() => {
        const elapsed = performance.now() / 1000;
        model.y = app.renderer.height * 0.54 + (reduced.matches ? 0 : Math.sin(elapsed * 0.85) * 2);
        model.x = app.renderer.width / 2;
        // Neutral breathing; no random sleeping or looping gestures during chat.
      });
    }).catch(() => { if (!disposed) setError('Không tải được nhân vật Live2D. Bạn vẫn có thể chat.'); });
    return () => {
      disposed = true;
      director.current = null;
      document.removeEventListener('visibilitychange', onVisibility);
      reduced.removeEventListener('change', reset);
      observer.disconnect();
      releaseGaze();
      reactions.destroy();
      player?.destroy();
      app.destroy(false, { children: true });
    };
  }, []);
  return <>{error && <p role="alert">{error}</p>}<canvas ref={canvas} id="live2d-canvas" className="live2d-canvas" /></>;
}
