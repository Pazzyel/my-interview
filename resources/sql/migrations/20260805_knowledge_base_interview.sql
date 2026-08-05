-- Knowledge-base interview workflow (MySQL 8+).

ALTER TABLE `knowledge_bases`
  ADD COLUMN `question_gen_status` ENUM('NONE','QUEUED','PROCESSING','COMPLETED','FAILED') NOT NULL DEFAULT 'NONE',
  ADD COLUMN `question_gen_error` VARCHAR(500) NULL,
  ADD COLUMN `question_gen_task_id` VARCHAR(36) NULL,
  ADD COLUMN `question_gen_config` TEXT NULL,
  ADD COLUMN `question_gen_message` VARCHAR(500) NULL,
  ADD COLUMN `question_gen_saved_count` INT NOT NULL DEFAULT 0,
  ADD COLUMN `question_gen_skipped_count` INT NOT NULL DEFAULT 0,
  ADD COLUMN `question_gen_updated_at` DATETIME NULL,
  ADD KEY `ix_kb_question_gen_status_updated` (`question_gen_status`, `question_gen_updated_at`);

CREATE TABLE IF NOT EXISTS `knowledge_base_questions` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `knowledge_base_id` INT NOT NULL,
  `skill_id` VARCHAR(64) NOT NULL DEFAULT 'knowledge-base',
  `difficulty` VARCHAR(16) NOT NULL DEFAULT 'mid',
  `type` VARCHAR(64) NULL,
  `category` VARCHAR(64) NOT NULL,
  `question` TEXT NOT NULL,
  `topic_summary` VARCHAR(300) NULL,
  `reference_answer` TEXT NULL,
  `key_points_json` TEXT NULL,
  `scoring_rubric` TEXT NULL,
  `follow_ups_json` TEXT NULL,
  `source_context` TEXT NULL,
  `kb_content_hash` VARCHAR(64) NULL,
  `status` ENUM('DRAFT','ACTIVE','ARCHIVED','STALE') NOT NULL DEFAULT 'DRAFT',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `ix_kb_question_kb_status` (`knowledge_base_id`, `status`),
  KEY `ix_kb_question_skill_difficulty` (`skill_id`, `difficulty`),
  CONSTRAINT `fk_kb_question_knowledge_base_id` FOREIGN KEY (`knowledge_base_id`) REFERENCES `knowledge_bases` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

ALTER TABLE `interview_sessions`
  ADD COLUMN `source_type` VARCHAR(32) NOT NULL DEFAULT 'NORMAL',
  ADD COLUMN `knowledge_base_id` INT NULL,
  ADD COLUMN `interview_category` VARCHAR(64) NULL,
  ADD KEY `ix_interview_sessions_knowledge_base_id` (`knowledge_base_id`);
