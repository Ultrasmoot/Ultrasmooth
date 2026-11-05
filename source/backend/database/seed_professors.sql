-- Demo professors.
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
