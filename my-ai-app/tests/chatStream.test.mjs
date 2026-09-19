import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readChatStream } from '../src/api/chatStream.ts';

function stream(text, chunkSize = 1) {
  const bytes = new TextEncoder().encode(text);
  return new ReadableStream({ start(controller) {
    for (let offset = 0; offset < bytes.length; offset += chunkSize) controller.enqueue(bytes.slice(offset, offset + chunkSize));
    controller.close();
  } });
}

test('Vietnamese UTF-8 and SSE boundaries can split across arbitrary bytes', async () => {
  const updates = [];
  const result = await readChatStream(stream('event: delta\ndata: {"text":"Chào "}\n\nevent: delta\ndata: {"text":"bạn"}\n\nevent: complete\ndata: {"reply_vi":"Chào bạn!"}\n\n'), (text) => updates.push(text));
  assert.equal(result.reply_vi, 'Chào bạn!');
  assert.deepEqual(updates, ['Chào ', 'Chào bạn', 'Chào bạn!']);
});

test('replacement after tool resolution does not append the old partial reply', async () => {
  const updates = [];
  await readChatStream(stream('event: delta\ndata: {"text":"Đang lưu"}\r\n\r\nevent: replace\ndata: {"text":""}\r\n\r\nevent: delta\ndata: {"text":"Đã lưu"}\r\n\r\nevent: complete\ndata: {"reply_vi":"Đã lưu"}\r\n\r\n', 9), (text) => updates.push(text));
  assert.deepEqual(updates, ['Đang lưu', '', 'Đã lưu', 'Đã lưu']);
});

test('EOF without a complete event must not be presented as success', async () => {
  await assert.rejects(readChatStream(stream('event: delta\ndata: {"text":"Chưa xong"}\n\n'), () => {}), /ngắt trước khi hoàn thành/);
});

test('backend failure propagates its message and releases reader', async () => {
  const body = stream('event: error\ndata: {"message":"Không thể lưu MySQL"}\n\n');
  await assert.rejects(readChatStream(body, () => {}), /Không thể lưu MySQL/);
  assert.equal(body.locked, false);
});

test('complete without final newline is accepted', async () => {
  const result = await readChatStream(stream('event: complete\ndata: {"reply_vi":"Xong"}'), () => {});
  assert.equal(result.reply_vi, 'Xong');
});

test('an empty final reply is rejected', async () => {
  await assert.rejects(readChatStream(stream('event: complete\ndata: {"reply_vi":""}\n\n'), () => {}), /trống/);
});

test('abort-like reader error is propagated, not treated as EOF', async () => {
  const body = new ReadableStream({ start(controller) { controller.error(new DOMException('Stopped', 'AbortError')); } });
  await assert.rejects(readChatStream(body, () => {}), { name: 'AbortError' });
  assert.equal(body.locked, false);
});
