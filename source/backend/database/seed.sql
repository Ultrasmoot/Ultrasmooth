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

INSERT INTO maintenance_records (resource_id, reported_by, description, status, issue_date, confirmed_by, confirmed_at)
SELECT r.id, a.id, 'Left controller not tracking', 'Open', CURDATE(), a.id, NOW()
FROM resources r JOIN users a ON a.email = 'admin@ku.th'
WHERE r.resource_code = 'RES-0004';

INSERT INTO maintenance_records (resource_id, reported_by, description, status, issue_date)
SELECT r.id, u.id, 'Laser cutter lens looks cracked', 'Reported', CURDATE()
FROM resources r JOIN users u ON u.email = 'student@ku.th'
WHERE r.resource_code = 'RES-0005';

-- check-in database
INSERT INTO bookings (resource_id, requester_id, start_time, end_time, purpose, status, decided_by, decided_at)
SELECT r.id, u.id, NOW() - INTERVAL 1 DAY, NOW() + INTERVAL 7 DAY,
       'Demo booking for check-in', 'Approved', a.id, NOW()
FROM resources r
JOIN users u ON u.email = 'student@ku.th'
JOIN users a ON a.email = 'admin@ku.th'
WHERE r.resource_code = 'RES-0001';

-- Details for the sample resources, plus a room (capacity, floor, facilities).
UPDATE resources SET building = 'Building 15', floor_level = 'Floor 1',
       features = '3D printing,PLA filament provided,Ventilated area',
       usage_notes = 'Prints up to 25 x 21 x 21 cm. Remove your print and clean the bed before you check out.'
WHERE resource_code = 'RES-0001';
UPDATE resources SET building = 'Building 15', floor_level = 'Floor 2',
       features = '4 channels,100 MHz,USB export',
       usage_notes = 'For debugging circuits and measuring signals. Do not connect mains voltage.'
WHERE resource_code = 'RES-0002';
UPDATE resources SET building = 'Building 15', floor_level = 'Floor 2',
       features = 'Temperature control,Fume extractor',
       usage_notes = 'Wear safety glasses. Switch off the iron and leave it to cool when finished.'
WHERE resource_code = 'RES-0003';
UPDATE resources SET building = 'Building 15', floor_level = 'Floor 3',
       features = 'Headset,2 controllers,Play area 3 x 3 m',
       usage_notes = 'For usability tests and VR demos. Clear the play area before use.'
WHERE resource_code = 'RES-0004';
UPDATE resources SET building = 'Building 15', floor_level = 'Floor 1',
       features = 'Cuts acrylic and wood,Extraction fan',
       usage_notes = 'Staff must be present for the first use. Never leave it running unattended.'
WHERE resource_code = 'RES-0005';

INSERT INTO resources (resource_code, name, type, category, location, owner, status,
                       building, floor_level, capacity, features, usage_notes) VALUES
('RES-0006', 'Meeting Room A', 'Room', 'Rooms', 'Building 15 - Room 301', 'Lab Administrator', 'Available',
 'Building 15', 'Floor 3', 30,
 'Projector,Whiteboard,Power outlets at every seat,Air conditioning,Wi-Fi',
 'For seminars, group meetings and thesis rehearsals. Please leave the room tidy.')
ON DUPLICATE KEY UPDATE resource_code = resource_code;

-- Demo professors. They share the demo student's password, so they are for demos only -
-- never keep these accounts in a real deployment. (Admins will add real professors in
-- Iteration 6, User Management.)
INSERT INTO users (full_name, email, password_hash, role, faculty, is_active, email_verified)
SELECT p.full_name, p.email, s.password_hash, 'professor', 'Engineering', 1, 1
FROM users s
JOIN (
    SELECT 'Assoc. Prof. Somchai Jaidee' AS full_name, 'somchai@ku.th' AS email
    UNION ALL SELECT 'Asst. Prof. Naree Wongsawat', 'naree@ku.th'
    UNION ALL SELECT 'Dr. Anan Preecha', 'anan@ku.th'
    UNION ALL SELECT 'Dr. Pimchanok Rattana', 'pimchanok@ku.th'
    UNION ALL SELECT 'Asst. Prof. Kittipong Suk', 'kittipong@ku.th'
) p
WHERE s.email = 'student@ku.th'
  AND NOT EXISTS (SELECT 1 FROM users x WHERE x.email = p.email);

INSERT INTO professor_profiles (user_id, expertise, bio)
SELECT u.id, v.expertise, v.bio
FROM users u
JOIN (
    SELECT 'somchai@ku.th' AS email, 'Software testing,Requirements engineering' AS expertise,
           'Test automation, acceptance testing and requirements elicitation.' AS bio
    UNION ALL SELECT 'naree@ku.th', 'Machine learning,Data science',
           'Applied machine learning, model evaluation and datasets for small projects.'
    UNION ALL SELECT 'anan@ku.th', 'Databases,System architecture',
           'Schema design, query tuning, MVC and modular architectures.'
    UNION ALL SELECT 'pimchanok@ku.th', 'HCI / UX,Usability testing',
           'Interface design, user studies and accessibility.'
    UNION ALL SELECT 'kittipong@ku.th', 'Security,Computer networks',
           'Authentication, secure deployment and network design.'
) v ON v.email = u.email
WHERE NOT EXISTS (SELECT 1 FROM professor_profiles x WHERE x.user_id = u.id);

-- One open request (the professor sees it in the inbox) and one that was declined with a reason.
INSERT INTO appointments (student_id, professor_id, topic, details, start_time, end_time,
                          status, decision_reason, decided_at, created_at)
SELECT s.id, p.id, v.topic, v.details, v.start_time, v.start_time + INTERVAL 30 MINUTE,
       v.status, v.reason, v.decided_at, NOW()
FROM users s
JOIN (
    SELECT 'somchai@ku.th' AS professor_email, 'How should we test our lab management system?' AS topic,
           'We have unit tests for the backend but nothing for the web pages.' AS details,
           CURDATE() + INTERVAL 5 DAY + INTERVAL 10 HOUR AS start_time, 'Pending' AS status,
           NULL AS reason, NULL AS decided_at
    UNION ALL SELECT 'anan@ku.th', 'Is a modular monolith the right choice for our project?',
           NULL, CURDATE() + INTERVAL 3 DAY + INTERVAL 14 HOUR, 'Declined',
           'I am travelling that week - please ask again after 10 Nov.', NOW()
) v ON 1 = 1
JOIN users p ON p.email = v.professor_email
WHERE s.email = 'student@ku.th';

-- A little history and a few unread notifications so the log, the dashboard and the bell
-- are not empty on the first look.
INSERT INTO activity_log (actor_id, actor_name, action, resource_id, target_type, target_id, summary, created_at)
SELECT u.id, u.full_name, v.action, r.id, v.target_type, NULL, v.summary, NOW() - INTERVAL v.hours_ago HOUR
FROM (
    SELECT 'student@ku.th' AS email, 'booking.submitted' AS action, 'RES-0001' AS code, 'booking' AS target_type,
           '3D Printer - Prusa MK3 - Print enclosure prototype' AS summary, 50 AS hours_ago
    UNION ALL SELECT 'admin@ku.th', 'booking.approved', 'RES-0001', 'booking', '3D Printer - Prusa MK3 for Demo Student', 49
    UNION ALL SELECT 'student@ku.th', 'checkin.done', 'RES-0001', 'booking', '3D Printer - Prusa MK3', 26
    UNION ALL SELECT 'student@ku.th', 'checkout.done', 'RES-0001', 'booking', '3D Printer - Prusa MK3', 24
    UNION ALL SELECT 'student@ku.th', 'maintenance.reported', 'RES-0004', 'maintenance', 'VR Headset - Meta Quest 3: left controller not tracking', 20
    UNION ALL SELECT 'admin@ku.th', 'maintenance.confirmed', 'RES-0004', 'maintenance', 'VR Headset - Meta Quest 3: left controller not tracking', 19
    UNION ALL SELECT 'student@ku.th', 'checkin.code_failed', 'RES-0001', 'booking', '3D Printer - Prusa MK3 (2 attempts left)', 4
) v
JOIN users u ON u.email = v.email
LEFT JOIN resources r ON r.resource_code = v.code;

INSERT INTO notifications (user_id, kind, title, body, link_view, created_at)
SELECT u.id, v.kind, v.title, v.body, v.link_view, NOW()
FROM (
    SELECT 'student@ku.th' AS email, 'appointment.decided' AS kind, 'Appointment declined' AS title,
           'Dr. Anan Preecha: "I am travelling that week - please ask again after 10 Nov."' AS body, 'appointments' AS link_view
    UNION ALL SELECT 'somchai@ku.th', 'appointment.requested', 'New appointment request',
           'Demo Student - How should we test our lab management system?', 'appointments'
    UNION ALL SELECT 'admin@ku.th', 'booking.submitted', 'New booking request',
           'Demo Student requested a booking. Open Requests to review it.', 'bookings'
) v
JOIN users u ON u.email = v.email;
