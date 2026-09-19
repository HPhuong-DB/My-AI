const http = require('node:http');
const fs = require('node:fs/promises');
const path = require('node:path');
const types = { '.html':'text/html; charset=utf-8', '.js':'text/javascript', '.css':'text/css', '.json':'application/json', '.png':'image/png', '.jpg':'image/jpeg', '.svg':'image/svg+xml', '.wasm':'application/wasm', '.moc3':'application/octet-stream' };
function createStaticServer(root) {
  root = path.resolve(root);
  return http.createServer(async (request, response) => {
    try {
      if (!['GET','HEAD'].includes(request.method)) { response.writeHead(405).end(); return; }
      const pathname = decodeURIComponent(new URL(request.url, 'http://127.0.0.1').pathname);
      const file = path.resolve(root, '.' + (pathname === '/' ? '/index.html' : pathname));
      if (!file.startsWith(root + path.sep) || pathname.split('/').some(part => part.startsWith('.'))) { response.writeHead(403).end(); return; }
      const real = await fs.realpath(file);
      if (!real.startsWith((await fs.realpath(root)) + path.sep)) { response.writeHead(403).end(); return; }
      const bytes = await fs.readFile(real);
      response.writeHead(200, { 'Content-Type':types[path.extname(real)] || 'application/octet-stream', 'X-Content-Type-Options':'nosniff', 'Cache-Control':'no-cache' });
      response.end(request.method === 'HEAD' ? undefined : bytes);
    } catch { response.writeHead(404).end('Not found'); }
  });
}
module.exports = { createStaticServer };
