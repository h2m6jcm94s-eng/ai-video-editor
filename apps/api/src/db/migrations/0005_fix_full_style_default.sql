-- Repair projects created with the invalid "full_style" default.
-- "full_style" was never a valid STYLE_TIER value; map existing rows to the
-- closest semantic equivalent (full_remix) so downstream render logic sees a
-- valid enum value.
UPDATE projects SET style_tier = 'full_remix' WHERE style_tier = 'full_style';
