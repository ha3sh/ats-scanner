# ats-scanner

Local ATS resume scanner: compare a resume against a job description, entirely
on your machine. No outbound requests, no telemetry, no stored uploads.

See `docs/ARCHITECTURE.md` for the design and `docs/SPEC.md`.

## Requirements

- [uv](https://docs.astral.sh/uv/) — Python (3.12, installed by uv if missing)

## Setup

```
uv run poe install
```

## Checks

```
uv run poe check    # lint + typecheck + test
```

Individual tasks: `uv run poe lint | format | typecheck | test`.

## Status

Skeleton and tooling only. No routes, no launcher, no pipeline yet — see
`docs/ROADMAP.md`.
