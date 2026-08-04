-- Voice interview module migration (MySQL 8+).
-- Safe to rerun because all objects are created with IF NOT EXISTS.
-- TODO(multi-user): user_id is a compatibility placeholder only. Authentication,
-- ownership checks, and tenant isolation are not implemented.

CREATE TABLE IF NOT EXISTS `voice_interview_sessions` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `user_id` VARCHAR(64) NOT NULL DEFAULT 'default',
  `role_type` VARCHAR(128) NOT NULL,
  `skill_id` VARCHAR(64) NOT NULL DEFAULT 'java-backend',
  `difficulty` VARCHAR(16) NOT NULL DEFAULT 'mid',
  `custom_jd_text` TEXT NULL,
  `resume_id` INT NULL,
  `intro_enabled` BOOLEAN NOT NULL DEFAULT FALSE,
  `tech_enabled` BOOLEAN NOT NULL DEFAULT TRUE,
  `project_enabled` BOOLEAN NOT NULL DEFAULT TRUE,
  `hr_enabled` BOOLEAN NOT NULL DEFAULT TRUE,
  `llm_provider` VARCHAR(50) NOT NULL DEFAULT 'default',
  `current_phase` ENUM('INTRO','TECH','PROJECT','HR','COMPLETED') NOT NULL,
  `status` ENUM('IN_PROGRESS','PAUSED','COMPLETED','FAILED') NOT NULL DEFAULT 'IN_PROGRESS',
  `planned_duration` INT NOT NULL DEFAULT 30,
  `actual_duration` INT NULL,
  `total_paused_seconds` INT NOT NULL DEFAULT 0,
  `start_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `end_time` DATETIME NULL,
  `paused_at` DATETIME NULL,
  `resumed_at` DATETIME NULL,
  `evaluate_status` ENUM('PENDING','PROCESSING','COMPLETED','FAILED') NULL,
  `evaluate_error` VARCHAR(500) NULL,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `ix_voice_sessions_user_created` (`user_id`, `created_at`),
  KEY `ix_voice_sessions_status_updated` (`status`, `updated_at`),
  KEY `ix_voice_sessions_evaluate_updated` (`evaluate_status`, `updated_at`),
  KEY `ix_voice_sessions_skill_id` (`skill_id`),
  KEY `ix_voice_sessions_resume_id` (`resume_id`),
  CONSTRAINT `fk_voice_sessions_resume_id` FOREIGN KEY (`resume_id`) REFERENCES `resumes` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `voice_interview_messages` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `session_id` INT NOT NULL,
  `message_type` ENUM('USER_SPEECH','AI_SPEECH','SYSTEM','SUMMARY') NOT NULL,
  `phase` ENUM('INTRO','TECH','PROJECT','HR','COMPLETED') NULL,
  `user_recognized_text` TEXT NULL,
  `ai_generated_text` TEXT NULL,
  `sequence_num` INT NOT NULL,
  `summary_covered_sequence` INT NULL,
  `timestamp` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_voice_messages_session_sequence` (`session_id`, `sequence_num`),
  KEY `ix_voice_messages_session_type_sequence` (`session_id`, `message_type`, `sequence_num`),
  CONSTRAINT `fk_voice_messages_session_id` FOREIGN KEY (`session_id`) REFERENCES `voice_interview_sessions` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `voice_interview_evaluations` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `session_id` INT NOT NULL,
  `overall_score` INT NULL,
  `overall_feedback` TEXT NULL,
  `question_evaluations_json` TEXT NULL,
  `strengths_json` TEXT NULL,
  `improvements_json` TEXT NULL,
  `reference_answers_json` TEXT NULL,
  `interviewer_role` VARCHAR(128) NULL,
  `interview_date` DATETIME NULL,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_voice_evaluations_session_id` (`session_id`),
  CONSTRAINT `fk_voice_evaluations_session_id` FOREIGN KEY (`session_id`) REFERENCES `voice_interview_sessions` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
