// Emit only the allowlisted portal assets using Vercel Build Output API v3.
import {mkdir, readFile, writeFile, rm} from 'node:fs/promises';
import {fileURLToPath, pathToFileURL} from 'node:url';
import {dirname, resolve} from 'node:path';
const here = dirname(fileURLToPath(import.meta.url));
export function apiOrigin(value) {
  let url;
  try { url = new URL(value); } catch { throw Error('Set CARTPOLE_API_ORIGIN to the HTTPS origin of the rig API.'); }
  if (url.protocol !== 'https:' || url.username || url.password || url.pathname !== '/' || url.search || url.hash || !url.hostname.includes('.') || ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname)) {
    throw Error('CARTPOLE_API_ORIGIN must be an HTTPS origin without credentials, path, query, or fragment.');
  }
  return url.origin;
}
export async function build(value, output = resolve(here, '.vercel/output')) {
  const origin = apiOrigin(value);
  const assets = resolve(here, '../../src/cartpole_sdk/portal/web');
  await rm(output, {recursive: true, force: true});
  await mkdir(resolve(output, 'static'), {recursive: true});
  for (const name of ['index.html', 'style.css', 'app.js', 'video.js']) {
    await writeFile(resolve(output, 'static', name), await readFile(resolve(assets, name)));
  }
  await writeFile(resolve(output, 'static/config.js'), 'window.CARTPOLE_CONFIG = Object.freeze(' + JSON.stringify({apiOrigin: origin, hosted: true}) + ');\n');
  const csp = `default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' blob:; connect-src 'self' ${origin}; font-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'; object-src 'none'`;
  const configuration = {version: 3, routes: [
    {src: '/(.*)', headers: {'Content-Security-Policy': csp, 'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer', 'Permissions-Policy': 'camera=(), microphone=(), geolocation=()', 'Cache-Control': 'no-store'}, continue: true},
    {src: '/', dest: '/index.html'},
    {handle: 'filesystem'},
  ]};
  await writeFile(resolve(output, 'config.json'), JSON.stringify(configuration, null, 2) + '\n');
}
if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  await build(process.env.CARTPOLE_API_ORIGIN);
  console.log('Built static portal assets with one authenticated HTTPS API origin. No API secrets included.');
}
