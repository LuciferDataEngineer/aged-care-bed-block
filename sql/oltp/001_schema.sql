-- Operational service registry. Loaded from the GEN aged care service lists.
-- Yearly snapshots are applied later as inserts, updates and deletes.

CREATE SCHEMA IF NOT EXISTS registry;

CREATE TABLE IF NOT EXISTS registry.providers (
    provider_id text PRIMARY KEY,
    provider_name text NOT NULL,
    organisation_type text,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS registry.services (
    service_id text PRIMARY KEY,
    provider_id text NOT NULL REFERENCES registry.providers (provider_id),
    service_name text NOT NULL,
    care_type text NOT NULL,
    state_code text NOT NULL,
    acpr_name text,
    suburb text,
    address text,
    postcode text,
    latitude double precision,
    longitude double precision,
    residential_places integer,
    home_care_places integer,
    restorative_places integer,
    source_year integer NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS registry.places_by_year (
    service_id text NOT NULL,
    year integer NOT NULL,
    residential_places integer,
    home_care_places integer,
    restorative_places integer,
    state_code text,
    acpr_name text,
    care_type text,
    PRIMARY KEY (service_id, year)
);
