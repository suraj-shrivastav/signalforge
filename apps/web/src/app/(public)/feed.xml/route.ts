export const dynamic = "force-static";

const FEED = `<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>SignalForge</title>
  <id>urn:signalforge:feed</id>
  <updated>1970-01-01T00:00:00Z</updated>
</feed>
`;

export function GET(): Response {
  return new Response(FEED, {
    headers: { "Content-Type": "application/atom+xml; charset=utf-8" },
  });
}
