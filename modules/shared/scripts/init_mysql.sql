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
  file_hash VARCHAR(128) NOT NULL,
  minio_path VARCHAR(512) NOT NULL,
  upload_user VARCHAR(128),
  document_version VARCHAR(64),
  authority_level VARCHAR(32),
  parse_status VARCHAR(64),
  parse_error TEXT,
  status VARCHAR(64) NOT NULL DEFAULT 'uploaded',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_document_hash (file_hash),
  INDEX idx_document_corpus_id (corpus_id)
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
  embedding_vector JSON,
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

-- 文档更新任务（README §2.7）
CREATE TABLE IF NOT EXISTS doc_update_job (
  job_id BIGINT PRIMARY KEY AUTO_INCREMENT,
  corpus_id BIGINT NOT NULL,
  document_id BIGINT NOT NULL,
  job_type VARCHAR(64) NOT NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'pending',
  phase VARCHAR(64),
  progress INT DEFAULT 0,
  message TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  finished_at TIMESTAMP NULL,
  INDEX idx_doc_update_corpus_id (corpus_id),
  INDEX idx_doc_update_document_id (document_id)
);

-- 智能问答会话（v0.2.0 新增，Demo 延后）
CREATE TABLE IF NOT EXISTS chat_session (
  session_id BIGINT PRIMARY KEY AUTO_INCREMENT,
  corpus_id BIGINT,
  created_by VARCHAR(128),
  title VARCHAR(255) DEFAULT '新对话',
  status VARCHAR(32) DEFAULT 'active',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_chat_session_corpus_id (corpus_id)
);

-- 对话消息（v0.2.0 新增，Demo 延后）
CREATE TABLE IF NOT EXISTS chat_message (
  message_id BIGINT PRIMARY KEY AUTO_INCREMENT,
  session_id BIGINT NOT NULL,
  role VARCHAR(16) NOT NULL,
  message_type VARCHAR(32) DEFAULT 'text',
  content JSON NOT NULL,
  intent VARCHAR(64),
  intent_params JSON,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_chat_msg_session_id (session_id)
);

-- ===================== m05 数据集生命周期 =====================
-- 评测集版本（冻结元数据快照）
CREATE TABLE IF NOT EXISTS dataset_version (
  version_id INT PRIMARY KEY AUTO_INCREMENT,
  corpus_id INT NOT NULL,
  version_number VARCHAR(64) NOT NULL,
  status VARCHAR(32) DEFAULT 'draft',
  case_count INT DEFAULT 0,
  coverage_report_id INT,
  split_config JSON,
  snapshot_metadata JSON,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  frozen_at TIMESTAMP NULL,
  INDEX idx_dataset_version_corpus_id (corpus_id)
);

-- 评测样本（单条 case；retired 标记保留审计，不参与统计与导出）
CREATE TABLE IF NOT EXISTS eval_case (
  case_id INT PRIMARY KEY AUTO_INCREMENT,
  version_id INT NOT NULL,
  case_uid VARCHAR(64) NOT NULL,
  intent_id VARCHAR(64),
  question TEXT NOT NULL,
  type VARCHAR(64),
  scope VARCHAR(64),
  difficulty VARCHAR(32),
  gold_answer TEXT,
  must_have_points JSON,
  acceptable_answers JSON,
  evidence JSON,
  eiu_ids JSON,
  content_priority VARCHAR(32),
  review_status VARCHAR(32) DEFAULT 'candidate',
  source VARCHAR(32) DEFAULT 'native',
  retired BOOLEAN DEFAULT FALSE,
  UNIQUE KEY uniq_case_uid (case_uid),
  INDEX idx_eval_case_version_id (version_id)
);

-- m02 覆盖率报告快照（供 m05 冻结版本 coverage_report_id 外键引用）
CREATE TABLE IF NOT EXISTS coverage_report (
  report_id INT PRIMARY KEY AUTO_INCREMENT,
  corpus_id INT NOT NULL,
  total_eiu INT DEFAULT 0,
  questionable_eiu INT DEFAULT 0,
  excluded_eiu INT DEFAULT 0,
  by_priority JSON,
  by_type JSON,
  by_document JSON,
  by_section JSON,
  weighted_coverage FLOAT DEFAULT 0,
  p0_coverage_pct FLOAT DEFAULT 0,
  block_reconciliation JSON,
  alerts JSON,
  snapshot_metadata JSON,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_coverage_report_corpus_id (corpus_id)
);
