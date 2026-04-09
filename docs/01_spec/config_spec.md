# Configuration Specification

## Priority

CLI arguments > environment variables > config.yaml > defaults

---

## Sections

### llm
- provider
- model
- api_key
- base_url
- temperature

### storage
- endpoint
- bucket
- prefixes

### mode
- dry_run

### steam
- api_url

### musicbrainz
- app_name
- version
- contact

### acoustid
- api_key
- thresholds

### search
- language strategy

### retry
- max_attempts
- backoff

### format
- conversion limits
