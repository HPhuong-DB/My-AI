create database brain_ai;
use brain_ai;

CREATE table chat_history(
id int AUTO_INCREMENT PRIMARY KEY,
role ENUM('user','ai') NOT NULL,
content TEXT not null,
timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
token_count INT DEFAULT 0
)ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE core_memories (
    id INT AUTO_INCREMENT PRIMARY KEY,
    memory_type VARCHAR(50) NOT NULL COMMENT 'Phân loại',
    fact TEXT NOT NULL COMMENT 'Nội dung',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
)ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE user_profiles (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) NOT NULL COMMENT 'Tên bạn',
    affection_level INT DEFAULT 0 COMMENT 'Thanh độ thân thiết',
    last_interaction DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Tự động cập nhật giờ mỗi khi có thay đổi'
)ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE system_configs (
    config_key VARCHAR(100) PRIMARY KEY COMMENT 'Tên cấu hình',
    config_value TEXT NOT NULL,
    description TEXT
)ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

