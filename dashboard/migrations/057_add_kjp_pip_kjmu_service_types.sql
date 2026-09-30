ALTER TABLE layanan_records
    DROP CONSTRAINT IF EXISTS layanan_records_service_type_check;

ALTER TABLE layanan_records
    ADD CONSTRAINT layanan_records_service_type_check
    CHECK (
        service_type IN (
            'ijazah', 'skpi', 'legalisasi', 'mutasi', 'kjp', 'pip', 'kjmu'
        )
    );
