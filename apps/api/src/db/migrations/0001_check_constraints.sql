-- CHECK constraints for enum columns
ALTER TABLE projects
  ADD CONSTRAINT projects_status_chk CHECK (status IN ('uploading', 'processing', 'complete', 'failed')),
  ADD CONSTRAINT projects_style_tier_chk CHECK (style_tier IN ('cuts_only', 'color_grade', 'with_text', 'with_effects', 'full_remix')),
  ADD CONSTRAINT projects_mode_chk CHECK (mode IN ('auto', 'assisted'));

ALTER TABLE assets
  ADD CONSTRAINT assets_type_chk CHECK (type IN ('reference_video', 'song', 'clip', 'render', 'preview', 'subtitle', 'lut', 'sfx'));

ALTER TABLE renders
  ADD CONSTRAINT renders_status_chk CHECK (status IN ('queued', 'running', 'complete', 'failed'));
