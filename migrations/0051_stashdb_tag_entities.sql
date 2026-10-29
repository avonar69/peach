-- StashDB 的作品标签与规范标签关系共享身份，索引与口味证据读取同一份关系。
-- 批量关系写入完成后统一刷新受影响作品的搜索索引。
DROP TRIGGER IF EXISTS asset_search_relation_insert;

CREATE TEMP TABLE stashdb_tag_map(name TEXT PRIMARY KEY,normalized TEXT NOT NULL,entity_id INTEGER);
INSERT OR IGNORE INTO stashdb_tag_map(name,normalized)
SELECT DISTINCT trim(tag),lower(trim(tag)) FROM asset_tag
WHERE source='auto:stashdb-tags' AND trim(tag)<>'';

INSERT OR IGNORE INTO entity(kind,canonical_name,normalized_name,created_at,updated_at)
SELECT 'tag',t.name,t.normalized,
       strftime('%Y-%m-%dT%H:%M:%fZ','now'),strftime('%Y-%m-%dT%H:%M:%fZ','now')
FROM stashdb_tag_map t
WHERE NOT EXISTS(SELECT 1 FROM entity e WHERE e.kind='tag'
      AND (e.normalized_name=t.normalized OR e.canonical_name=t.name));

UPDATE stashdb_tag_map SET entity_id=(SELECT e.id FROM entity e WHERE e.kind='tag'
  AND (e.normalized_name=stashdb_tag_map.normalized OR e.canonical_name=stashdb_tag_map.name)
  ORDER BY e.id LIMIT 1);

INSERT OR IGNORE INTO asset_entity(asset_id,entity_id,role,source,confidence,metadata_json,first_seen_at,last_seen_at)
SELECT t.asset_id,m.entity_id,
       'tag',t.source,coalesce(t.confidence,1),'{}',
       strftime('%Y-%m-%dT%H:%M:%fZ','now'),strftime('%Y-%m-%dT%H:%M:%fZ','now')
FROM asset_tag t JOIN asset a ON a.id=t.asset_id JOIN stashdb_tag_map m ON m.name=trim(t.tag)
WHERE t.source='auto:stashdb-tags';

DROP TABLE stashdb_tag_map;

DELETE FROM asset_search WHERE asset_id IN (SELECT asset_id FROM asset_tag WHERE source='auto:stashdb-tags');
INSERT INTO asset_search(asset_id,name,code,entities,search_terms)
SELECT asset_id,name,code,entities,search_terms FROM asset_search_source
WHERE asset_id IN (SELECT asset_id FROM asset_tag WHERE source='auto:stashdb-tags');

CREATE TRIGGER asset_search_relation_insert AFTER INSERT ON asset_entity BEGIN
  DELETE FROM asset_search WHERE asset_id=NEW.asset_id;
  INSERT INTO asset_search(asset_id,name,code,entities,search_terms)
  SELECT asset_id,name,code,entities,search_terms FROM asset_search_source WHERE asset_id=NEW.asset_id;
END;
