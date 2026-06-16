CREATE TABLE IF NOT EXISTS products (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  source_code   TEXT UNIQUE NOT NULL,
  jan_code      TEXT,
  name          TEXT NOT NULL,
  clean_name    TEXT,
  series        TEXT,
  maker         TEXT,
  category      TEXT DEFAULT 'gacha',
  play_price    INTEGER,
  release_month TEXT,
  release_date  DATE,
  release_text  TEXT,
  is_reprint    INTEGER DEFAULT 0,
  overseas_ng   INTEGER DEFAULT 0,
  capsule_size  TEXT,
  lot_qty       INTEGER,
  ip_tag        TEXT,
  image_url     TEXT,
  detail_url    TEXT,
  source        TEXT DEFAULT 'amuzu',
  source_priority INTEGER DEFAULT 10,
  first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS release_changes (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  source_code   TEXT NOT NULL,
  changed_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  field         TEXT NOT NULL,
  old_value     TEXT,
  new_value     TEXT,
  UNIQUE(source_code, changed_at, field)
);

CREATE TABLE IF NOT EXISTS affiliate_links (
  product_id INTEGER NOT NULL,
  asp        TEXT NOT NULL,
  url        TEXT NOT NULL,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (product_id, asp)
);

CREATE TABLE IF NOT EXISTS post_log (
  product_id INTEGER NOT NULL,
  channel    TEXT NOT NULL,
  posted_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (product_id, channel)
);

CREATE INDEX IF NOT EXISTS idx_products_release_month ON products(release_month);
CREATE INDEX IF NOT EXISTS idx_products_maker ON products(maker);
CREATE INDEX IF NOT EXISTS idx_products_first_seen ON products(first_seen_at);
CREATE INDEX IF NOT EXISTS idx_release_changes_code ON release_changes(source_code);
