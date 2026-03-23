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
  `resume_id` INT NOT NULL,
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
  KEY `ix_interview_sessions_resume_id` (`resume_id`),
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
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_knowledge_bases_file_hash` (`file_hash`)
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

