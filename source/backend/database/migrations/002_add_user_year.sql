ALTER TABLE users
    ADD COLUMN year TINYINT UNSIGNED NULL AFTER major,
    ADD CONSTRAINT chk_users_year CHECK (year IS NULL OR year BETWEEN 1 AND 6);
-- Existing undergraduate rows have no year yet; users can be asked to fill it in
-- (or an admin sets it in Iteration 6 user management).
UPDATE users SET year = 3 WHERE email = 'student@ku.th' AND year IS NULL;  -- demo account only