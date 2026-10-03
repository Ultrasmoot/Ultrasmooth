-- Demo/seed data - NOT for production. Runs automatically on first container start (after schema.sql) so the team doesn't have to add
-- an admin or sample resources by hand before recording a demo.
--   email: admin@ku.th
--   password: Admin1234

INSERT INTO users (full_name, email, password_hash, role, is_active)
VALUES ('Demo Admin','admin@ku.th','$2b$12$5tqw9Pys0YT/.0XQRwAt4.SGOPnyb4n/5n72MRmSrTVqe9HyKA.DS','admin',1)
ON DUPLICATE KEY UPDATE email = email;

INSERT INTO resources (resource_code, name, type, category, location, owner, status) VALUES
('RES-0001', '3D Printer - Prusa MK3','Equipment', 'Fabrication', 'Lab A - Room 101', 'Demo Admin', 'Available'),
('RES-0002', 'Oscilloscope - Tektronix','Equipment', 'Electronics', 'Lab B - Room 204', 'Demo Admin', 'In Use'),
('RES-0003', 'Soldering Station','Tool','Electronics', 'Lab B - Room 204', 'Demo Admin', 'Available'),
('RES-0004', 'VR Headset - Meta Quest 3','Equipment', 'Computing',   'Lab C - Room 310', 'Demo Admin', 'Maintenance'),
('RES-0005', 'Laser Cutter','Equipment', 'Fabrication', 'Lab A - Room 101', 'Demo Admin', 'Available')
ON DUPLICATE KEY UPDATE resource_code = resource_code;

-- Sample requests belong to the demo student (not the admin), so the student
-- sees them under "My requests" and the admin sees the Pending one in the queue.
--   email:    student@ku.th
--   password: Student1234
INSERT INTO users (student_id, full_name, email, password_hash, role, faculty, major, is_active)
VALUES (
    '6610000001',
    'Demo Student',
    'student@ku.th',
    '$2b$12$k8ZmYpkiEVIj7AwMXb5c4eJKaSRfY.SbAJzTfOvf7AVrq2xkj/2ZC',
    'undergrad_student',
    'Engineering',
    'Computer Engineering',
    1
)
ON DUPLICATE KEY UPDATE email = email;

INSERT INTO bookings (resource_id, requester_id, start_time, end_time, purpose, status)
SELECT v.resource_id, u.id, v.start_time, v.end_time, v.purpose, v.status
FROM users u
JOIN (
    SELECT 1 AS resource_id, '2026-10-05 09:00:00' AS start_time, '2026-10-05 11:00:00' AS end_time, 'Print enclosure prototype' AS purpose, 'Pending'  AS status
    UNION ALL
    SELECT 2, '2026-10-06 13:00:00', '2026-10-06 15:00:00', 'Debug signal noise issue',   'Approved'
    UNION ALL
    SELECT 3, '2026-10-04 10:00:00', '2026-10-04 12:00:00', 'Soldering workshop prep',    'Rejected'
) v
WHERE u.email = 'student@ku.th';
