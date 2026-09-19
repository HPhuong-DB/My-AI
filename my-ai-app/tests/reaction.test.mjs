import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { planReaction, readingDuration } from '../src/avatar/reaction.ts';
import { createReactionController } from '../src/avatar/reactionController.ts';

const cases = [
  ['Chào cậu, rất vui được gặp lại!', 'warm'],
  ['Chúc mừng bạn đã sửa được lỗi!', 'celebrate'],
  ['Mình rất tiếc vì bạn mất hết bài làm.', 'comfort'],
  ['Mình không buồn nữa.', 'neutral'],
  ['Chưa cần chúc mừng đâu bạn.', 'neutral'],
  ['Buồn là một trạng thái cảm xúc.', 'neutral'],
  ['Mình rất tiếc, việc đó không thành công. Đừng vội chúc mừng.', 'comfort'],
  ['Ngủ ngon nhé bạn!', 'goodnight'],
  ['Bạn tìm ra nó ở đâu vậy?', 'curious'],
  ['Biến `happy` chứa chuỗi "chúc mừng".', 'neutral'],
  ['Định nghĩa của từ buồn là một trạng thái cảm xúc.', 'neutral'],
  ['Bạn tên là Hà. Bạn đang học Python.', 'neutral'],
  ['Tên file là "ngủ ngon".', 'neutral'],
];
for (const [text, kind] of cases) test(`reaction: ${text}`, () => assert.equal(planReaction(text).kind, kind));

test('longer replies remain readable; gesture never outlives subtitle', () => {
  assert.ok(readingDuration('Một đoạn giải thích dài. '.repeat(25)) > readingDuration('Chào!'));
  assert.equal(readingDuration('từ '.repeat(10_000)), 30_000);
  for (const [text] of cases) {
    const plan = planReaction(text);
    assert.ok(plan.holdMs <= plan.displayMs);
    assert.ok(plan.displayMs >= 4000);
  }
});

test('every selected asset exists in the actual model manifest', () => {
  const root = new URL('../public/live2d/huohuo/', import.meta.url);
  const manifest = JSON.parse(readFileSync(new URL('huohuo.model3.json', root))).FileReferences;
  for (const [text] of cases) {
    const plan = planReaction(text);
    if (plan.motion) {
      const file = manifest.Motions[plan.motion][0].File;
      const duration = JSON.parse(readFileSync(new URL(file, root))).Meta.Duration * 1000;
      assert.ok(plan.holdMs <= duration, `${plan.motion} should play at most once`);
    }
    if (plan.expression) {
      const definition = manifest.Expressions.find((item) => item.Name === plan.expression);
      assert.ok(definition);
      JSON.parse(readFileSync(new URL(definition.File, root)));
    }
    assert.ok(!['angry', 'white eyes', 'qizi1', 'qizi2'].includes(plan.expression));
  }
});

function fixture() {
  let now = 0;
  const timers = [];
  const calls = [];
  const director = createReactionController({ now: () => now,
    schedule(fn, ms) { const timer = { fn, at: now + ms }; timers.push(timer); return timer; },
    cancel(timer) { if (timer) timer.cancelled = true; },
  });
  const player = { play: (plan) => calls.push(plan), reset: () => calls.push('reset') };
  return { director, calls, player, timers, advance(ms) {
    now += ms;
    for (const timer of timers) if (!timer.cancelled && timer.at <= now) { timer.cancelled = true; timer.fn(); }
  } };
}

test('late timer from previous answer cannot clear the new expression', () => {
  const f = fixture(); f.director.attach(f.player);
  f.director.play(planReaction('Chúc mừng bạn!'));
  const stale = f.timers[0].fn;
  f.advance(1000); f.director.play(planReaction('Mình rất tiếc.'));
  const count = f.calls.length;
  stale(); assert.equal(f.calls.length, count);
  f.advance(4000); assert.equal(f.calls.at(-1), 'reset');
});

test('model loaded too late never replays an expired response', () => {
  const f = fixture(); f.director.play(planReaction('Chào cậu!'));
  f.advance(5000); f.director.attach(f.player);
  assert.deepEqual(f.calls, ['reset']);
});

test('loading model receives only remaining reaction time', () => {
  const f = fixture(); f.director.play(planReaction('Chào cậu!'));
  f.advance(1000); f.director.attach(f.player);
  assert.equal(f.calls.at(-1).holdMs, 2500);
  f.advance(2500); assert.equal(f.calls.at(-1), 'reset');
});

test('same gesture has a cooldown, expressions can still react', () => {
  const f = fixture(); f.director.attach(f.player);
  const plan = planReaction('Chúc mừng cậu!');
  f.director.play(plan); assert.equal(f.calls.at(-1).motion, 'qizi');
  f.advance(5000); f.director.play(plan); assert.equal(f.calls.at(-1).motion, '');
  assert.equal(f.calls.at(-1).expression, 'warm');
  f.advance(8000); f.director.play(plan); assert.equal(f.calls.at(-1).motion, 'qizi');
});

test('reset and disposal discard pending reactions and timers', () => {
  const f = fixture(); f.director.play(planReaction('Chào cậu!'));
  f.director.reset(); f.director.attach(f.player);
  assert.deepEqual(f.calls, ['reset']);
  f.director.destroy(); const count = f.calls.length;
  f.director.play(planReaction('Chúc mừng cậu!')); f.advance(10_000);
  assert.equal(f.calls.length, count);
});
