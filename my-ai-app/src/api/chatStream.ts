import type { ChatStreamPayload } from '../types';

/** Incremental SSE decoder. A closed connection without complete is a failure. */
export async function readChatStream(body: ReadableStream<Uint8Array>, onText: (text: string) => void): Promise<ChatStreamPayload> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let reply = '';
  let complete: ChatStreamPayload | undefined;
  const process = (block: string) => {
    const lines = block.split(/\r?\n/);
    const event = lines.find((line) => line.startsWith('event:'))?.slice(6).trim();
    const data = lines.filter((line) => line.startsWith('data:')).map((line) => line.slice(5).trimStart()).join('\n');
    if (!data) return;
    const payload = JSON.parse(data) as ChatStreamPayload;
    if (event === 'error') throw new Error(payload.message || 'Phản hồi bị gián đoạn. Hãy thử lại.');
    if (event === 'delta') { reply += payload.text || ''; onText(reply); }
    if (event === 'replace') { reply = payload.text || ''; onText(reply); }
    if (event === 'complete') {
      if (!payload.reply_vi?.trim()) throw new Error('Câu trả lời trống. Hãy thử lại.');
      complete = payload;
      onText(payload.reply_vi);
    }
  };
  try {
    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      const blocks = buffer.split(/\r?\n\r?\n/);
      buffer = blocks.pop() || '';
      blocks.forEach(process);
      if (complete || done) break;
    }
    if (!complete && buffer.trim()) process(buffer);
    if (!complete) throw new Error('Kết nối bị ngắt trước khi hoàn thành. Hãy thử lại.');
    return complete;
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}
