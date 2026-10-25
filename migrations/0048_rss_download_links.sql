-- RSS/Atom 条目的原始下载地址；媒体文件仍经下载任务落地。
ALTER TABLE feed_item ADD COLUMN download_links_json TEXT NOT NULL DEFAULT '[]';
