ALTER TABLE bookings
    MODIFY COLUMN status ENUM('Pending','Approved','Rejected','Cancelled') NOT NULL DEFAULT 'Pending',
    ADD COLUMN cancelled_at DATETIME NULL AFTER decision_reason;
