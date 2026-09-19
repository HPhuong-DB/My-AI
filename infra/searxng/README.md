# Local SearXNG for Huohuo

## Requirements

- Docker Desktop for macOS
- Docker Compose v2 (`docker compose version`)

## Start

From this directory:

```bash
docker compose up -d
```

Check the containers:

```bash
docker compose ps
```

Check the JSON API:

```bash
curl 'http://127.0.0.1:8080/search?q=ollama&format=json'
```

Open the UI at <http://127.0.0.1:8080>.

## Connect Huohuo

In `my-ai-app/backend/.env`, add:

```env
WEB_SEARCH_PROVIDER=searxng
WEB_SEARCH_URL=http://127.0.0.1:8080/search
```

Restart the FastAPI backend after changing `.env`.

## Stop and logs

```bash
docker compose logs -f searxng
docker compose down
```

This setup is intended for local use. Change `server.secret_key` in `settings.yml` before exposing the instance beyond localhost, and do not expose it publicly without rate limiting and access control.
