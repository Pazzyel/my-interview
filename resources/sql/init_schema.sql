CREATE TABLE IF NOT EXISTS `llm_provider_config` (
  `id` VARCHAR(64) NOT NULL,
  `base_url` VARCHAR(512) NOT NULL,
  `api_key_ciphertext` VARCHAR(4096) NOT NULL,
  `api_key_nonce` VARCHAR(64) NOT NULL,
  `model` VARCHAR(128) NOT NULL,
  `embedding_model` VARCHAR(128) NULL,
  `embedding_dimensions` INT NULL,
  `supports_embedding` BOOLEAN NOT NULL DEFAULT FALSE,
  `temperature` DOUBLE NOT NULL DEFAULT 0,
  `enabled` BOOLEAN NOT NULL DEFAULT TRUE,
  `builtin` BOOLEAN NOT NULL DEFAULT FALSE,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `llm_global_setting` (
  `id` INT NOT NULL DEFAULT 1,
  `default_chat_provider_id` VARCHAR(64) NOT NULL,
  `default_embedding_provider_id` VARCHAR(64) NOT NULL,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  CONSTRAINT `fk_llm_default_chat_provider` FOREIGN KEY (`default_chat_provider_id`) REFERENCES `llm_provider_config` (`id`),
  CONSTRAINT `fk_llm_default_embedding_provider` FOREIGN KEY (`default_embedding_provider_id`) REFERENCES `llm_provider_config` (`id`),
  CONSTRAINT `ck_llm_global_setting_singleton` CHECK (`id` = 1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `interview_schedule` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `company_name` VARCHAR(255) NOT NULL,
  `position` VARCHAR(255) NOT NULL,
  `interview_time` DATETIME NOT NULL,
  `interview_type` ENUM('ONSITE','VIDEO','PHONE') NULL,
  `meeting_link` TEXT NULL,
  `round_number` INT NOT NULL DEFAULT 1,
  `interviewer` VARCHAR(255) NULL,
  `notes` TEXT NULL,
  `status` ENUM('PENDING','COMPLETED','CANCELLED','RESCHEDULED') NOT NULL DEFAULT 'PENDING',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `ix_interview_schedule_time` (`interview_time`),
  KEY `ix_interview_schedule_status_time` (`status`, `interview_time`),
  CONSTRAINT `ck_interview_schedule_round_number` CHECK (`round_number` BETWEEN 1 AND 10)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `resumes` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `fileHash` VARCHAR(255) NOT NULL,
  `originalFilename` VARCHAR(255) NOT NULL,
  `fileSize` INT NOT NULL,
  `contentType` VARCHAR(100) NOT NULL,
  `storageKey` VARCHAR(255) NULL,
  `storageUrl` VARCHAR(255) NULL,
  `resumeText` TEXT NULL,
  `uploadedAt` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `lastAccessedAt` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `accessCount` INT NOT NULL DEFAULT 1,
  `analyzeStatus` ENUM('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED') NOT NULL DEFAULT 'PENDING',
  `analyzeError` TEXT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_resumes_fileHash` (`fileHash`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `resume_analyses` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `resume_id` INT NOT NULL,
  `overallScore` INT NULL,
  `contentScore` INT NULL,
  `structureScore` INT NULL,
  `skillMatchScore` INT NULL,
  `expressionScore` INT NULL,
  `projectScore` INT NULL,
  `summary` TEXT NULL,
  `strengthsJson` TEXT NULL,
  `suggestionsJson` TEXT NULL,
  `analyzedAt` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `ix_resume_analyses_resume_id` (`resume_id`),
  CONSTRAINT `fk_resume_analyses_resume_id` FOREIGN KEY (`resume_id`) REFERENCES `resumes` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `interview_sessions` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `session_id` VARCHAR(36) NOT NULL,
  `request_id` VARCHAR(64) NULL,
  `resume_id` INT NULL,
  `skill_id` VARCHAR(64) NOT NULL DEFAULT 'java-backend',
  `difficulty` VARCHAR(16) NOT NULL DEFAULT 'mid',
  `llm_provider` VARCHAR(50) NOT NULL DEFAULT 'default',
  `source_type` VARCHAR(32) NOT NULL DEFAULT 'NORMAL',
  `knowledge_base_id` INT NULL,
  `interview_category` VARCHAR(64) NULL,
  `total_questions` INT NOT NULL,
  `current_question_index` INT NOT NULL DEFAULT 0,
  `status` ENUM('CREATED', 'IN_PROGRESS', 'COMPLETED', 'EVALUATED') NOT NULL DEFAULT 'CREATED',
  `questions_json` TEXT NULL,
  `overall_score` INT NULL,
  `overall_feedback` TEXT NULL,
  `strengths_json` TEXT NULL,
  `improvements_json` TEXT NULL,
  `reference_answers_json` TEXT NULL,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `completed_at` DATETIME NULL,
  `evaluate_status` ENUM('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED') NOT NULL DEFAULT 'PENDING',
  `evaluate_error` VARCHAR(500) NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_interview_sessions_session_id` (`session_id`),
  UNIQUE KEY `uq_interview_sessions_request_id` (`request_id`),
  KEY `ix_interview_sessions_resume_id` (`resume_id`),
  KEY `ix_interview_sessions_skill_created` (`skill_id`, `created_at`),
  KEY `ix_interview_sessions_knowledge_base_id` (`knowledge_base_id`),
  CONSTRAINT `fk_interview_sessions_resume_id` FOREIGN KEY (`resume_id`) REFERENCES `resumes` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `interview_answers` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `session_pk_id` INT NOT NULL,
  `question_index` INT NOT NULL,
  `question` TEXT NULL,
  `category` VARCHAR(100) NULL,
  `user_answer` TEXT NULL,
  `score` INT NULL,
  `feedback` TEXT NULL,
  `reference_answer` TEXT NULL,
  `key_points_json` TEXT NULL,
  `answered_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `ix_interview_answers_session_pk_id` (`session_pk_id`),
  CONSTRAINT `fk_interview_answers_session_pk_id` FOREIGN KEY (`session_pk_id`) REFERENCES `interview_sessions` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `voice_interview_sessions` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `user_id` VARCHAR(64) NOT NULL DEFAULT 'default' COMMENT 'Reserved for future multi-user support; no ownership enforcement yet',
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

CREATE TABLE IF NOT EXISTS `knowledge_bases` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `file_hash` VARCHAR(64) NOT NULL,
  `name` VARCHAR(255) NOT NULL,
  `category` VARCHAR(100) NULL,
  `original_filename` VARCHAR(255) NOT NULL,
  `file_size` INT NOT NULL,
  `content_type` VARCHAR(100) NULL,
  `storage_key` VARCHAR(500) NULL,
  `storage_url` VARCHAR(1000) NULL,
  `uploaded_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `last_accessed_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `access_count` INT NOT NULL DEFAULT 1,
  `question_count` INT NOT NULL DEFAULT 0,
  `vector_status` ENUM('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED') NOT NULL DEFAULT 'PENDING',
  `vector_error` VARCHAR(500) NULL,
  `chunk_count` INT NOT NULL DEFAULT 0,
  `question_gen_status` ENUM('NONE', 'QUEUED', 'PROCESSING', 'COMPLETED', 'FAILED') NOT NULL DEFAULT 'NONE',
  `question_gen_error` VARCHAR(500) NULL,
  `question_gen_task_id` VARCHAR(36) NULL,
  `question_gen_config` TEXT NULL,
  `question_gen_message` VARCHAR(500) NULL,
  `question_gen_saved_count` INT NOT NULL DEFAULT 0,
  `question_gen_skipped_count` INT NOT NULL DEFAULT 0,
  `question_gen_updated_at` DATETIME NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_knowledge_bases_file_hash` (`file_hash`),
  KEY `ix_kb_question_gen_status_updated` (`question_gen_status`, `question_gen_updated_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

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
  `status` ENUM('DRAFT', 'ACTIVE', 'ARCHIVED', 'STALE') NOT NULL DEFAULT 'DRAFT',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `ix_kb_question_kb_status` (`knowledge_base_id`, `status`),
  KEY `ix_kb_question_skill_difficulty` (`skill_id`, `difficulty`),
  CONSTRAINT `fk_kb_question_knowledge_base_id` FOREIGN KEY (`knowledge_base_id`) REFERENCES `knowledge_bases` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `rag_chat_sessions` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `title` VARCHAR(255) NOT NULL,
  `status` VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `message_count` INT NOT NULL DEFAULT 0,
  `is_pinned` BOOLEAN NOT NULL DEFAULT FALSE,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `rag_chat_messages` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `session_id` INT NOT NULL,
  `type` VARCHAR(20) NOT NULL,
  `content` TEXT NOT NULL,
  `message_order` INT NOT NULL,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `completed` BOOLEAN NOT NULL DEFAULT TRUE,
  PRIMARY KEY (`id`),
  KEY `ix_rag_chat_messages_session_id` (`session_id`),
  CONSTRAINT `fk_rag_chat_messages_session_id` FOREIGN KEY (`session_id`) REFERENCES `rag_chat_sessions` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `rag_session_knowledge_bases` (
  `session_id` INT NOT NULL,
  `knowledge_base_id` INT NOT NULL,
  PRIMARY KEY (`session_id`, `knowledge_base_id`),
  FOREIGN KEY (`session_id`) REFERENCES `rag_chat_sessions` (`id`) ON DELETE CASCADE,
  FOREIGN KEY (`knowledge_base_id`) REFERENCES `knowledge_bases` (`id`) ON DELETE CASCADE
);

