ALTER TABLE laporan_form_fields DROP CONSTRAINT IF EXISTS laporan_form_fields_field_type_check;
ALTER TABLE laporan_form_fields ADD CONSTRAINT laporan_form_fields_field_type_check
CHECK (field_type IN ('text', 'textarea', 'radio', 'checkbox', 'file', 'date', 'number', 'rating', 'dropdown', 'time', 'email', 'header', 'info', 'link'));
