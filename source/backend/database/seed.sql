-- Demo/seed data — NOT for production. Runs automatically on first
-- container start (after schema.sql) so the team doesn't have to add
-- an admin or sample resources by hand before recording a demo.
--
-- Admin login for demos:
--   email:    admin@ku.th
--   password: Admin1234
--
-- Student login for demos (owner of the sample requests below):
--   email:    student@ku.th
--   password: Student1234

INSERT INTO users (full_name, email, password_hash, role, is_active, email_verified)
VALUES (
    'Lab Administrator',
    'admin@ku.th',
    '$2b$12$5tqw9Pys0YT/.0XQRwAt4.SGOPnyb4n/5n72MRmSrTVqe9HyKA.DS',
    'admin',
    1,
    1
)
ON DUPLICATE KEY UPDATE email = email;

INSERT INTO resources (resource_code, name, type, category, location, owner, status) VALUES
('RES-0001', '3D Printer - Prusa MK3',     'Equipment', 'Fabrication', 'Lab A - Room 101', 'Lab Administrator', 'Available'),
('RES-0002', 'Oscilloscope - Tektronix',   'Equipment', 'Electronics', 'Lab B - Room 204', 'Lab Administrator', 'Available'),
('RES-0003', 'Soldering Station',          'Tool',      'Electronics', 'Lab B - Room 204', 'Lab Administrator', 'Available'),
('RES-0004', 'VR Headset - Meta Quest 3',  'Equipment', 'Computing',   'Lab C - Room 310', 'Lab Administrator', 'Maintenance'),
('RES-0005', 'Laser Cutter',               'Equipment', 'Fabrication', 'Lab A - Room 101', 'Lab Administrator', 'Available')
ON DUPLICATE KEY UPDATE resource_code = resource_code;

-- Sample requests belong to the demo student (not the admin), so the student
-- sees them under "My requests" and the admin sees the Pending one in the queue.
INSERT INTO users (student_id, full_name, email, password_hash, role, faculty, major, year, is_active, email_verified)
VALUES (
    '6610000001',
    'Demo Student',
    'student@ku.th',
    '$2b$12$k8ZmYpkiEVIj7AwMXb5c4eJKaSRfY.SbAJzTfOvf7AVrq2xkj/2ZC',
    'undergrad_student',
    'Engineering',
    'Computer Engineering',
    3,
    1,
    1
)
ON DUPLICATE KEY UPDATE email = email;

INSERT INTO bookings (resource_id, requester_id, start_time, end_time, purpose, status)
SELECT v.resource_id, u.id, v.start_time, v.end_time, v.purpose, v.status
FROM users u 
JOIN (
    -- Dates are relative to "now" so the demo never goes stale. The Pending request starts
    -- after the check-in demo booking below (which runs until +7 days) so approving it
    -- does not hit the "overlaps an approved booking" rule.
    SELECT 1 AS resource_id, CURDATE() + INTERVAL 10 DAY + INTERVAL 9 HOUR AS start_time, CURDATE() + INTERVAL 10 DAY + INTERVAL 11 HOUR AS end_time, 'Print enclosure prototype' AS purpose, 'Pending'  AS status
    UNION ALL
    SELECT 2, CURDATE() + INTERVAL 4 DAY + INTERVAL 13 HOUR, CURDATE() + INTERVAL 4 DAY + INTERVAL 15 HOUR, 'Debug signal noise issue',   'Approved'
    UNION ALL
    SELECT 3, CURDATE() + INTERVAL 2 DAY + INTERVAL 10 HOUR, CURDATE() + INTERVAL 2 DAY + INTERVAL 12 HOUR, 'Soldering workshop prep',    'Rejected'
) v
WHERE u.email = 'student@ku.th';

-- check-in database
INSERT INTO bookings (resource_id, requester_id, start_time, end_time, purpose, status, decided_by, decided_at)
SELECT r.id, u.id, NOW() - INTERVAL 1 DAY, NOW() + INTERVAL 7 DAY,
       'Demo booking for check-in', 'Approved', a.id, NOW()
FROM resources r
JOIN users u ON u.email = 'student@ku.th'
JOIN users a ON a.email = 'admin@ku.th'
WHERE r.resource_code = 'RES-0001';
