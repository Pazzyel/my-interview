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
