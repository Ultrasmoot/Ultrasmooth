CREATE TABLE IF NOT EXISTS activity_log (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    actor_id INT NULL,
    actor_name VARCHAR(150) NOT NULL,
    action VARCHAR(40) NOT NULL,
    resource_id INT NULL,
    target_type VARCHAR(30) NULL,
    target_id INT NULL,
    summary VARCHAR(500) NOT NULL,
    created_at DATETIME NOT NULL,
    INDEX idx_activity_created (created_at),
    INDEX idx_activity_actor (actor_id, created_at),
    INDEX idx_activity_action (action, created_at),
    INDEX idx_activity_resource (resource_id, created_at),
    FOREIGN KEY (actor_id) REFERENCES users(id) ON DELETE SET NULL,
    FOREIGN KEY (resource_id) REFERENCES resources(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS notifications (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    kind VARCHAR(40) NOT NULL,
    title VARCHAR(150) NOT NULL,
    body VARCHAR(500) NOT NULL DEFAULT '',
    link_view VARCHAR(30) NOT NULL DEFAULT 'home',
    is_read TINYINT(1) NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL,
    INDEX idx_notifications_user (user_id, is_read, created_at),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
