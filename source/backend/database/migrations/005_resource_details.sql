ALTER TABLE resources
    ADD COLUMN building VARCHAR(100) NULL AFTER status,
    ADD COLUMN floor_level VARCHAR(50) NULL AFTER building,
    ADD COLUMN capacity INT UNSIGNED NULL AFTER floor_level,
    ADD COLUMN features VARCHAR(500) NULL AFTER capacity,
    ADD COLUMN usage_notes VARCHAR(1000) NULL AFTER features;
