-- The schema of the live database, as of 2026-09-16, when the droplet was
-- running revision b50fe89.
--
-- It is here so that tests/test_database.py can prove a pull request still
-- deploys: there are no migrations, so live is upgraded by create_all() plus
-- add_missing_columns() over exactly this, and only some changes survive that
-- (see CLAUDE.md, "There are still no migrations").
--
-- Live's database was built by create_all() from b50fe89's models, so this is
-- reproducible rather than dumped off the box. To refresh it when live moves,
-- run (from the repo root, with <rev> the new revision reported by
-- /api/get_version):
--
--   python tests/live_schema/refresh.py <rev>
--
-- which writes tests/live_schema/<today>_<rev>.sql. Commit the new file,
-- delete the old one, and point SNAPSHOT in tests/test_database.py at it. The
-- file name carries the revision, so a stale snapshot is visible.
CREATE TABLE association_table (
	user_id BINARY(16) NOT NULL,
	item_id BINARY(16) NOT NULL,
	PRIMARY KEY (user_id, item_id),
	FOREIGN KEY(user_id) REFERENCES users (id),
	FOREIGN KEY(item_id) REFERENCES items (id)
);
CREATE TABLE games (
	id BINARY(16) NOT NULL,
	time_created DATETIME DEFAULT CURRENT_TIMESTAMP,
	active BOOLEAN NOT NULL,
	ai_shot_review_enabled BOOLEAN NOT NULL,
	ai_auto_actions_enabled BOOLEAN NOT NULL,
	ai_escalation_enabled BOOLEAN NOT NULL,
	ai_resolve_everything_enabled BOOLEAN NOT NULL,
	exclusion_circle_lat FLOAT,
	exclusion_circle_long FLOAT,
	exclusion_circle_radius FLOAT,
	next_circle_lat FLOAT,
	next_circle_long FLOAT,
	next_circle_radius FLOAT,
	drop_circle_lat FLOAT,
	drop_circle_long FLOAT,
	drop_circle_radius FLOAT,
	ticker_update_tag INTEGER,
	PRIMARY KEY (id)
);
CREATE TABLE items (
	id BINARY(16) NOT NULL,
	time_created DATETIME DEFAULT CURRENT_TIMESTAMP,
	item_type VARCHAR(7),
	data VARCHAR,
	collected_only_once BOOLEAN NOT NULL,
	collected_as_team BOOLEAN NOT NULL,
	game_id BINARY(16),
	PRIMARY KEY (id),
	FOREIGN KEY(game_id) REFERENCES games (id)
);
CREATE TABLE shots (
	id BINARY(16) NOT NULL,
	time_created DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
	game_id BINARY(16) NOT NULL,
	user_id BINARY(16) NOT NULL,
	target_user_id BINARY(16),
	team_id BINARY(16) NOT NULL,
	shot_damage INTEGER,
	shot_timeout FLOAT NOT NULL,
	image_base64 VARCHAR NOT NULL,
	checked BOOLEAN NOT NULL,
	result VARCHAR,
	location_context VARCHAR,
	heading FLOAT,
	ai_review_state VARCHAR,
	ai_review VARCHAR,
	ai_escalation_state VARCHAR,
	ai_escalation VARCHAR,
	admin_notes VARCHAR,
	appeal_state VARCHAR,
	appealed_at FLOAT,
	shooter_appeal_reason VARCHAR,
	target_appeal_reason VARCHAR,
	PRIMARY KEY (id),
	FOREIGN KEY(game_id) REFERENCES games (id),
	FOREIGN KEY(user_id) REFERENCES users (id),
	FOREIGN KEY(target_user_id) REFERENCES users (id),
	FOREIGN KEY(team_id) REFERENCES teams (id)
);
CREATE TABLE teams (
	id BINARY(16) NOT NULL,
	time_created DATETIME DEFAULT CURRENT_TIMESTAMP,
	name VARCHAR,
	game_id BINARY(16) NOT NULL,
	identity_colour VARCHAR,
	PRIMARY KEY (id),
	FOREIGN KEY(game_id) REFERENCES games (id)
);
CREATE TABLE ticker_entries (
	id INTEGER NOT NULL,
	time_created DATETIME DEFAULT CURRENT_TIMESTAMP,
	game_id BINARY(16) NOT NULL,
	private_user_id BINARY(16),
	highlight_user_id BINARY(16),
	shot_id BINARY(16),
	message VARCHAR NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(game_id) REFERENCES games (id),
	FOREIGN KEY(private_user_id) REFERENCES users (id),
	FOREIGN KEY(highlight_user_id) REFERENCES users (id),
	FOREIGN KEY(shot_id) REFERENCES shots (id)
);
CREATE TABLE user_aliases (
	session_id BINARY(16) NOT NULL,
	user_id BINARY(16) NOT NULL,
	PRIMARY KEY (session_id),
	FOREIGN KEY(user_id) REFERENCES users (id)
);
CREATE TABLE users (
	id BINARY(16) NOT NULL,
	time_created DATETIME DEFAULT CURRENT_TIMESTAMP,
	last_seen DATETIME,
	name VARCHAR,
	game_id BINARY(16),
	team_id BINARY(16),
	num_bullets INTEGER NOT NULL,
	hit_points INTEGER NOT NULL,
	shot_timeout FLOAT NOT NULL,
	shot_damage INTEGER NOT NULL,
	appeals_remaining INTEGER NOT NULL,
	latitude FLOAT,
	longitude FLOAT,
	location_timestamp FLOAT,
	location_accuracy FLOAT,
	time_of_death FLOAT,
	identity_slot INTEGER,
	identity_overrides VARCHAR,
	identity_wardrobe VARCHAR,
	reference_photo_base64 VARCHAR,
	reference_review_state VARCHAR,
	reference_review VARCHAR,
	update_tag INTEGER,
	PRIMARY KEY (id),
	FOREIGN KEY(game_id) REFERENCES games (id),
	FOREIGN KEY(team_id) REFERENCES teams (id)
);
CREATE INDEX ix_ticker_entries_game_id ON ticker_entries (game_id);
CREATE INDEX ix_ticker_entries_highlight_user_id ON ticker_entries (highlight_user_id);
CREATE INDEX ix_ticker_entries_private_user_id ON ticker_entries (private_user_id);
CREATE INDEX ix_ticker_entries_shot_id ON ticker_entries (shot_id);
CREATE INDEX ix_user_aliases_user_id ON user_aliases (user_id);
CREATE INDEX ix_users_game_id ON users (game_id);
