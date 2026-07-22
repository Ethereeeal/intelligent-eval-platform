CREATE DATABASE IF NOT EXISTS evalforge DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE evalforge;

CREATE TABLE IF NOT EXISTS corpus (
  corpus_id BIGINT PRIMARY KEY AUTO_INCREMENT,
  name VARCHAR(255) NOT NULL,
  description TEXT,
  domain VARCHAR(128),
  created_by VARCHAR(128),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  version VARCHAR(64)
);

CREATE TABLE IF NOT EXISTS document (
  document_id BIGINT PRIMARY KEY AUTO_INCREMENT,
  corpus_id BIGINT NOT NULL,
  file_name VARCHAR(255) NOT NULL,
  file_type VARCHAR(64) NOT NULL,
  file_size BIGINT,
  content_hash VARCHAR(128) NOT NULL,
  minio_path VARCHAR(512) NOT NULL,
  upload_user VARCHAR(128),
  upload_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  document_version VARCHAR(64),
  parse_status VARCHAR(64),
  parse_error TEXT,
  INDEX idx_document_corpus_id (corpus_id),
  INDEX idx_document_hash (content_hash)
);

CREATE TABLE IF NOT EXISTS document_block (
  block_id BIGINT PRIMARY KEY AUTO_INCREMENT,
  document_id BIGINT NOT NULL,
  parent_block_id BIGINT NULL,
  section_path VARCHAR(512),
  page_no VARCHAR(64),
  block_type VARCHAR(64),
  block_text LONGTEXT,
  start_offset BIGINT,
  end_offset BIGINT,
  metadata_json JSON,
  embedding_id BIGINT,
  INDEX idx_block_document_id (document_id)
);

CREATE TABLE IF NOT EXISTS task_job (
  job_id BIGINT PRIMARY KEY AUTO_INCREMENT,
  job_type VARCHAR(64) NOT NULL,
  target_id BIGINT,
  status VARCHAR(64) NOT NULL,
  progress INT DEFAULT 0,
  error_message TEXT,
  started_at TIMESTAMP NULL,
  finished_at TIMESTAMP NULL
);
