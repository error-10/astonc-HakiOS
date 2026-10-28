// Minimal HTTPS fetcher: node scripts/fetch.js <url> <outfile>
const fs = require('fs');
const [url, out] = process.argv.slice(2);
if (!url || !out) {
  console.error('usage: node scripts/fetch.js <url> <outfile>');
  process.exit(2);
}
fetch(url, { headers: { 'User-Agent': 'node' } })
  .then(async (res) => {
    if (!res.ok) {
      console.error('http ' + res.status + ' ' + url);
      process.exit(1);
    }
    const buf = Buffer.from(await res.arrayBuffer());
    fs.writeFileSync(out, buf);
    console.log('saved ' + out + ' ' + buf.length + ' bytes');
  })
  .catch((e) => {
    console.error('error: ' + e.message);
    process.exit(1);
  });
