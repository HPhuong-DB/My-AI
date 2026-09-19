import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, writeFile, symlink, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createRequire } from 'node:module';
const { createStaticServer } = createRequire(import.meta.url)('../desktop/server.cjs');
test('desktop serves built assets but rejects escape paths, symlinks, directories and writes', async () => {
  const root = await mkdtemp(join(tmpdir(), 'huohuo-desktop-'));
  const outside = await mkdtemp(join(tmpdir(), 'huohuo-outside-'));
  try {
    await writeFile(join(root, 'index.html'), '<main>Huohuo</main>');
    await writeFile(join(outside, 'secret'), 'not public');
    await symlink(join(outside, 'secret'), join(root, 'link'));
    const server = createStaticServer(root);
    const request = (url, method = 'GET') => new Promise(resolve => {
      let status;
      server.emit('request', { url, method }, { writeHead(code) { status = code; return this; }, end(body) { resolve({ status, body: body?.toString() }); } });
    });
    assert.equal((await request('/')).body, '<main>Huohuo</main>');
    assert.equal((await request('/', 'HEAD')).body, undefined);
    assert.equal((await request('/', 'POST')).status, 405);
    assert.equal((await request('/%2e%2e%2fsecret')).status, 403);
    assert.equal((await request('/link')).status, 403);
    assert.equal((await request('/missing')).status, 404);
    assert.equal((await request('/%ZZ')).status, 404);
  } finally { await rm(root, { recursive: true, force: true }); await rm(outside, { recursive: true, force: true }); }
});
