import { test } from 'node:test';
import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import { createLive2DPlayer } from '../src/avatar/live2dPlayer.ts';
import { planReaction } from '../src/avatar/reaction.ts';

function fixture({ reduced = false, pendingMotion = false } = {}) {
  let now = 0;
  let resolveMotion;
  const calls = [];
  const values = [0.1, 0];
  const defaultExpression = { setFadeInTime: (value) => calls.push(['fade', value]) };
  const expressions = { defaultExpression, currentExpression: 'old-face', reserveExpressionIndex: 3,
    resetExpression: () => calls.push('neutral') };
  const manager = Object.assign(new EventEmitter(), {
    expressionManager: expressions,
    motionGroups: { qizi: [{ setIsLoop: (value) => calls.push(['loop', value]) }] },
    stopAllMotions: () => calls.push('stop'),
  });
  const internal = Object.assign(new EventEmitter(), { motionManager: manager, coreModel: {
    getParameterCount: () => values.length,
    getParameterValueByIndex: (index) => values[index],
    setParameterValueByIndex: (index, value) => { values[index] = value; },
  } });
  const model = { internalModel: internal,
    motion: (...args) => { calls.push(['motion', ...args]); return pendingMotion ? new Promise((resolve) => { resolveMotion = resolve; }) : Promise.resolve(true); },
    expression: (name) => { calls.push(['expression', name]); return Promise.resolve(true); },
  };
  const player = createLive2DPlayer(model, () => now, () => reduced);
  return { player, manager, internal, expressions, values, calls,
    resolveMotion: () => resolveMotion(true), advance: (ms) => { now += ms; internal.emit('beforeMotionUpdate'); } };
}

test('reset cancels pending expressions and removes the remembered previous face', () => {
  const f = fixture(); f.player.reset();
  assert.equal(f.expressions.reserveExpressionIndex, -1);
  assert.equal(f.expressions.currentExpression, f.expressions.defaultExpression);
  assert.ok(f.calls.includes('neutral'));
  assert.ok(!f.calls.some((call) => Array.isArray(call) && call[0] === 'expression' && call[1] === ''));
});

test('prop and posture parameters return to the initial pose after interruption', () => {
  const f = fixture(); f.values[0] = 1; f.values[1] = 0.8;
  f.player.reset(); f.advance(175);
  assert.ok(f.values[0] > 0.1 && f.values[0] < 1);
  f.advance(175); assert.ok(Math.abs(f.values[0] - 0.1) < 1e-6); assert.equal(f.values[1], 0);
});

test('cached and newly loaded motions are non-looping', () => {
  const f = fixture();
  assert.ok(f.calls.some((call) => Array.isArray(call) && call[0] === 'loop' && call[1] === false));
  let loop = true;
  f.manager.emit('motionLoaded', 'haoqi', 0, { setIsLoop: (value) => { loop = value; } });
  assert.equal(loop, false);
});

test('motion must start before expression is applied', async () => {
  const f = fixture(); f.player.play(planReaction('Chúc mừng cậu!'));
  await Promise.resolve(); await Promise.resolve();
  const actions = f.calls.filter(Array.isArray).map((call) => call[0]);
  assert.ok(actions.indexOf('motion') < actions.indexOf('expression'));
});

test('expired or cancelled asset load cannot apply a stale expression', async () => {
  const f = fixture({ pendingMotion: true });
  f.player.play(planReaction('Chúc mừng cậu!')); f.player.reset(); f.resolveMotion();
  await Promise.resolve(); await Promise.resolve();
  assert.ok(!f.calls.some((call) => Array.isArray(call) && call[0] === 'expression'));
});

test('reduced motion keeps the expression but skips the gesture', async () => {
  const f = fixture({ reduced: true }); f.player.play(planReaction('Chúc mừng cậu!'));
  await Promise.resolve();
  assert.ok(!f.calls.some((call) => Array.isArray(call) && call[0] === 'motion'));
  assert.ok(f.calls.some((call) => Array.isArray(call) && call[0] === 'expression' && call[1] === 'warm'));
});

test('unmount removes model listeners and ignores future playback', () => {
  const f = fixture(); f.player.destroy(); const count = f.calls.length;
  f.player.play(planReaction('Chúc mừng cậu!'));
  assert.equal(f.calls.length, count);
  assert.equal(f.manager.listenerCount('motionLoaded'), 0);
  assert.equal(f.internal.listenerCount('beforeMotionUpdate'), 0);
});
