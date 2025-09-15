setup:  ## install deps
\tpip install -e .
dev:    ## run api + workers
\tdocker-compose up --build
migrate:## run sql migration
\tpsql $$POSTGRES_URL -f infra/migrations/0001_init.sql
lint:
\trufflehog --fail || true
