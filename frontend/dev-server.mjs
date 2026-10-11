// In-process local runner for Windows environments that restrict child-process forks.
// Production uses Next.js standalone server.js built by Docker.
import { createServer } from "node:http";
import next from "next";
const hostname = "127.0.0.1";
const port = Number(process.env.PORT || 3000);
const app = next({ dev: true, hostname, port });
const handle = app.getRequestHandler();
await app.prepare();
createServer((request, response) => handle(request, response)).listen(port, hostname, () => {
  process.stdout.write(`PAXVEIL web ready on http://${hostname}:${port}\n`);
});
