const fs = require('node:fs');

// Never record credentials: only a harmless lifecycle event marker is written.
const forbidden = new Set(['forge_publish_token', 'npm_token', 'node_auth_token']);
if (Object.keys(process.env).some(key => forbidden.has(key.toLowerCase()))) {
  throw new Error('Publication credentials reached a lifecycle hook');
}
const event = process.env.npm_lifecycle_event;
if (!['prepack', 'prepare', 'postpack'].includes(event)) {
  throw new Error('Authenticated publication executed a lifecycle hook');
}
fs.appendFileSync('lifecycle-events.txt', `${event}\n`);
