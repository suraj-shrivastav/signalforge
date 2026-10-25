# Deploy on Railway

Two services from this repository, plus the database and image storage you already have on
Supabase. Railway no longer has a permanent free plan: new accounts get trial credit, then a
paid plan. Check the current pricing page before relying on it.

## Services

| Service | Root directory | Build | Start |
|---|---|---|---|
| `api` | repository root | Dockerfile `infra/railway/api.Dockerfile` | set in the Dockerfile |
| `web` | `apps/web` | Railpack (detects Next.js) | `npm start` (uses `PORT`) |

1. Create a Railway project from the GitHub repository.
2. **api:** add a service from the repo. Settings: Config as code path
   `infra/railway/api.railway.json`. Generate a public domain only if you need to call the API
   from Hermes; otherwise keep it private.
3. **web:** add a second service from the same repo, Root Directory `apps/web`. Generate a
   public domain (this is the site).
4. Set the variables below, then deploy both.

## Variables

**api** (copy the names from your local `.env`; never commit the values)

- `DATABASE_URL` (the Supabase pooler string)
- `EDITOR_API_KEY`, `AGENT_API_KEY` (32 or more random characters each)
- `SUPABASE_URL` (the API accepts images from this host) and `SUPABASE_SECRET_KEY` (the API uploads article images with it, so Hermes needs no Supabase key)
- `SITE_URL` (the public web URL, no trailing slash), `INDEXNOW_KEY`, `PUBLISH_BYLINE`
- `LLM_PROVIDER`, `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL_*`, `LLM_EXTRA_BODY`,
  `LLM_EMBED_EXTRA_BODY`, `LLM_MAX_OUTPUT_TOKENS`, `TAVILY_API_KEY` (the stages run inside the API)
- Optional: `AUTO_PIPELINE_ON_ACCEPT=true`, `AUTO_PIPELINE_DAILY_CAP`, `AI_TRAINING_CRAWLERS`

**web**

- `API_BASE_URL`: the api service's private address, `http://<api-service>.railway.internal:<PORT>`
  (or its public URL). Server side only.
- `SITE_URL`: the same public URL as above. `INDEXNOW_KEY`: same value as the api.
- `EDITOR_UI_PASSWORD` if you keep the editor pages.

**Hermes** (outside Railway): `API_BASE_URL` (public api URL), `EDITOR_API_KEY` set to the
agent key. No Supabase key: the api uploads the images. See `skills/article-images/SKILL.md`.

## Scheduling

Either let Hermes call `POST /agent/run/tick`, or add a third service from the same Dockerfile
with start command `python -m apps.worker.tick` and a cron schedule such as `*/30 * * * *`.
Use one of the two, not both.

## Check after deploy

1. `https://<api>/health` returns `{"status":"ok"}`.
2. The site shows the published articles; `/robots.txt`, `/sitemap.xml` and `/feed.xml` use the
   public domain.
3. `https://<site>/indexnow-key.txt` returns the key.
4. Publish or republish one article and confirm the IndexNow ping in the api logs.
5. `https://<site>/articles/<slug>/og.png` returns a PNG.
6. Share a link in a chat or social app to see the card.

## Not tested

The Dockerfile and the two `railway.json` files were written but not built or deployed from
here (no Docker daemon, no Railway login).
