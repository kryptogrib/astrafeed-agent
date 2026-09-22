# AstraFeed Token Brief

A small, self-hosted engine that collects public Telegram channel posts, filters and scores them, merges duplicate events, and renders a source-linked brief. The default brief language is English.

## Quickstart

```sh
cp config.example.yaml config.yaml
cp .env.example .env
make install
uv run astrafeed-brief --tokens SOL,OKB --window 24h --stub-llm
```

The stub command runs offline and prints a sample empty-window response. For live collection, fill in `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, and `TELEGRAM_SESSION` in `.env`, add public channel references to `config.yaml`, and set `OPENROUTER_API_KEY`.

Create a Telegram reader session with `make login`. Then run a one-shot brief:

```sh
uv run astrafeed-brief --tokens SOL,OKB --window 24h
```

Start continuous collection and the health endpoint with:

```sh
make serve
curl http://localhost:8000/healthz
```

The process polls configured channels and serves `/healthz` on the same event loop. To run it in a container, use `docker compose up --build`; the database is stored in the `astrafeed-data` volume.

## Development

- `make test` runs the pytest suite.
- `make lint` runs Ruff checks and confirms formatting.
- `make check` runs lint, type checking, and tests.

See [PROVENANCE.md](PROVENANCE.md) for extraction history and [docs/adr](docs/adr/) for retained architecture decisions.
