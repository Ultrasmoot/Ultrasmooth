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