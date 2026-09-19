import { test } from 'node:test';
import assert from 'node:assert/strict';
import { canPresentProactive } from '../src/api/proactiveGate.ts';
const now = Date.parse('2026-09-11T05:00:00Z');
const expires = new Date(now + 30_000).toISOString();
const ready = { visible: true, busy: false, typing: false, reading: false, local_hour: 12 };
test('fresh offer can be shown while present and idle', () => assert.equal(canPresentProactive(ready, expires, now), true));
for (const [field, value] of [['visible', false], ['busy', true], ['typing', true], ['reading', true], ['local_hour', 23], ['local_hour', 7]]) {
  test(`do not interrupt when ${field}=${value}`, () => assert.equal(canPresentProactive({ ...ready, [field]: value }, expires, now), false));
}
test('expired, missing and malformed deadlines are rejected', () => {
  for (const date of [undefined, 'invalid', new Date(now - 1).toISOString(), new Date(now + 60_000).toISOString()]) assert.equal(canPresentProactive(ready, date, now), false);
});
