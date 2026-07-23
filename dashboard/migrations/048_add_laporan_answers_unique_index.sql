DO $$
BEGIN
    IF to_regclass('public.laporan_submission_files') IS NOT NULL THEN
        WITH ranked AS (
            SELECT
                id,
                FIRST_VALUE(id) OVER (
                    PARTITION BY submission_id, field_id
                    ORDER BY id DESC
                ) AS keep_id,
                ROW_NUMBER() OVER (
                    PARTITION BY submission_id, field_id
                    ORDER BY id DESC
                ) AS rn
            FROM laporan_submission_answers
        )
        UPDATE laporan_submission_files sf
        SET answer_id = ranked.keep_id
        FROM ranked
        WHERE sf.answer_id = ranked.id
          AND ranked.rn > 1;
    END IF;
END $$;

WITH ranked AS (
    SELECT
        id,
        ROW_NUMBER() OVER (
            PARTITION BY submission_id, field_id
            ORDER BY id DESC
        ) AS rn
    FROM laporan_submission_answers
)
DELETE FROM laporan_submission_answers a
USING ranked
WHERE a.id = ranked.id
  AND ranked.rn > 1;

CREATE UNIQUE INDEX IF NOT EXISTS ux_laporan_submission_answers_submission_field
    ON laporan_submission_answers (submission_id, field_id);
