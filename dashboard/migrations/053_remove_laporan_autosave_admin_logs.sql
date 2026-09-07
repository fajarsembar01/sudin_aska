-- AUTOSAVE is a technical draft-persistence event and must not be counted as
-- an admin performance action. The application no longer includes these rows
-- in /overview/admin-performance; remove historical rows to reduce log noise.
DELETE FROM dashboard_admin_action_logs
WHERE feature_key = 'laporan'
  AND UPPER(TRIM(action)) = 'AUTOSAVE';
