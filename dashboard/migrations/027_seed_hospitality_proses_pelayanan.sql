-- Seed awal komponen & aspek Hospitality: Proses Pelayanan
INSERT INTO hospitality_components (name, description, sort_order, is_required, active)
VALUES ('Proses pelayanan', NULL, 0, TRUE, TRUE)
ON CONFLICT (LOWER(name)) DO NOTHING;

WITH comp AS (
    SELECT id FROM hospitality_components WHERE LOWER(name) = LOWER('Proses pelayanan') LIMIT 1
)
INSERT INTO hospitality_aspects (component_id, name, description, sort_order, is_required, active)
SELECT comp.id, aspect.name, aspect.description, aspect.sort_order, TRUE, TRUE
FROM comp
JOIN (
    VALUES
        ('Penyambutan tamu', NULL, 0),
        ('Pencatatan tamu', NULL, 1),
        ('Pelayanan sesuai kebutuhan tamu', NULL, 2),
        ('Penutupan dan pamitan', NULL, 3)
) AS aspect(name, description, sort_order) ON TRUE
WHERE NOT EXISTS (
    SELECT 1 FROM hospitality_aspects ha
    WHERE ha.component_id = comp.id
      AND LOWER(ha.name) = LOWER(aspect.name)
);
