CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    student_id VARCHAR(10) UNIQUE,
    full_name VARCHAR(150),
    email VARCHAR(150) NOT NULL UNIQUE,
    password_hash VARCHAR(255),
    google_sub VARCHAR(255) UNIQUE,
    role ENUM('phd_student','undergrad_student','professor','admin') NOT NULL,
    faculty VARCHAR(150),
    major VARCHAR(150),
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
