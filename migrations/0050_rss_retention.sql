-- RSS 保存期限与最小去重记忆；默认永久保存。
ALTER TABLE feed_source ADD COLUMN rss_retention_count INTEGER CHECK(rss_retention_count IS NULL OR rss_retention_count BETWEEN 1 AND 36500);
ALTER TABLE feed_source ADD COLUMN rss_retention_unit TEXT NOT NULL DEFAULT 'days' CHECK(rss_retention_unit IN ('days','months','years'));
ALTER TABLE feed_item ADD COLUMN rss_expired_at TEXT;
ALTER TABLE feed_item ADD COLUMN rss_merged_into INTEGER REFERENCES feed_item(id) ON DELETE CASCADE;
CREATE TABLE rss_item_identity (
    source_id INTEGER NOT NULL REFERENCES feed_source(id) ON DELETE CASCADE,
    identity TEXT NOT NULL,
    item_id INTEGER NOT NULL REFERENCES feed_item(id) ON DELETE CASCADE,
    PRIMARY KEY(source_id,identity)
);
CREATE INDEX rss_item_identity_item ON rss_item_identity(item_id);
CREATE INDEX rss_item_retention ON feed_item(source_id,rss_expired_at,first_seen);
INSERT INTO ledger_revision(tbl) VALUES('rss_item_identity');
CREATE TRIGGER rev_rss_item_identity_insert AFTER INSERT ON rss_item_identity BEGIN
  UPDATE ledger_revision SET n=n+1 WHERE tbl='rss_item_identity';
END;
CREATE TRIGGER rev_rss_item_identity_update AFTER UPDATE ON rss_item_identity BEGIN
  UPDATE ledger_revision SET n=n+1 WHERE tbl='rss_item_identity';
END;
CREATE TRIGGER rev_rss_item_identity_delete AFTER DELETE ON rss_item_identity BEGIN
  UPDATE ledger_revision SET n=n+1 WHERE tbl='rss_item_identity';
END;
