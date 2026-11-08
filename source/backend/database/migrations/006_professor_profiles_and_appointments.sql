CREATE TABLE IF NOT EXISTS professor_profiles (
    user_id INT PRIMARY KEY,
    expertise VARCHAR(500) NOT NULL DEFAULT '',
    bio VARCHAR(500) NOT NULL DEFAULT '',
    photo_path VARCHAR(255) NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS appointments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    student_id INT NOT NULL,
    professor_id INT NOT NULL,
    topic VARCHAR(100) NOT NULL,
    details VARCHAR(500) NULL,
    start_time DATETIME NOT NULL,
    end_time DATETIME NOT NULL,
    status ENUM('Pending','Accepted','Declined','Cancelled') NOT NULL DEFAULT 'Pending',
    decision_reason VARCHAR(255) NULL,
    decided_at DATETIME NULL,
    created_at DATETIME NOT NULL,
    INDEX idx_appt_professor (professor_id, status, start_time),
    INDEX idx_appt_student (student_id, status),
    FOREIGN KEY (student_id) REFERENCES users(id),
    FOREIGN KEY (professor_id) REFERENCES users(id)
);
