// Custom Next.js server — start cron jobs bij opstart
import { createServer } from 'http';
import { parse } from 'url';
import next from 'next';
import { startCronJobs } from './lib/cron';

const dev = process.env.NODE_ENV !== 'production';
const hostname = '0.0.0.0';
const port = parseInt(process.env.PORT ?? '3000', 10);

const app = next({ dev, hostname, port });
const handle = app.getRequestHandler();

app.prepare().then(() => {
  createServer(async (req, res) => {
    const parsedUrl = parse(req.url ?? '/', true);
    await handle(req, res, parsedUrl);
  }).listen(port, hostname, () => {
    console.log(`> Next Move Outreach klaar op http://${hostname}:${port}`);
    startCronJobs();
  });
});
