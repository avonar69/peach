-- RSS 展示只保存图片地址与来源级链接筛选偏好。
ALTER TABLE feed_item ADD COLUMN rss_images_json TEXT NOT NULL DEFAULT '{}';
ALTER TABLE feed_source ADD COLUMN hide_unsupported INTEGER NOT NULL DEFAULT 0 CHECK(hide_unsupported IN (0,1));
UPDATE feed_source SET etag=NULL,last_modified=NULL WHERE kind='rss';
