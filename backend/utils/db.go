package utils

import (
	"database/sql"
	"fmt"
	"os"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/stdlib"
)

var DB *sql.DB

// InitDB opens a pooled Supabase Postgres connection.
//
// In production this should be the Supavisor pooled DSN
// (port 6543, transaction mode) — Cloud Run fans out across many instances
// and the Supabase free tier caps direct (5432) connections around 60.
// Pass the DSN via the SUPABASE_DB_URL env var.
//
// The driver is pgx in SIMPLE-PROTOCOL mode. The transaction-mode pooler
// multiplexes many client connections onto fewer Postgres backends and can
// switch the backend between requests, so server-side prepared statements
// (lib/pq's default, and pgx's default cached mode) collide across
// connections — surfacing as intermittent errors like "unnamed prepared
// statement does not exist" or "bind message supplies N parameters, but
// prepared statement requires M". Simple protocol inlines parameters
// client-side and issues no prepared statements, the Go equivalent of the
// Python ingest side's psycopg `prepare_threshold=None`.
func InitDB() error {
	dsn := os.Getenv("SUPABASE_DB_URL")
	if dsn == "" {
		return fmt.Errorf("SUPABASE_DB_URL not set")
	}

	cfg, err := pgx.ParseConfig(dsn)
	if err != nil {
		return fmt.Errorf("parse SUPABASE_DB_URL: %w", err)
	}
	cfg.DefaultQueryExecMode = pgx.QueryExecModeSimpleProtocol

	db := stdlib.OpenDB(*cfg)
	if err := db.Ping(); err != nil {
		return err
	}

	// Keep the pool small per-instance; Cloud Run spawns many instances.
	db.SetMaxOpenConns(8)
	db.SetMaxIdleConns(4)

	DB = db
	fmt.Println("Connected to Supabase Postgres")
	return nil
}
