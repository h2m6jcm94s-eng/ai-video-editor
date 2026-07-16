# Verb Registry

Canonical list of editing verbs/effects in the system.
Generated from `services/shared-py/src/shared_py/verb_registry.py`.

| Verb | Category | Implemented | Prerequisites | Ledger Ref | Description |
|---|---|---|---|---|---|
| `trim_slot` | edit | yes | — | — | Change the duration of a cutlist slot. |
| `cut_slot` | edit | no | — | — | Split or remove a slot (planned). |
| `set_transition` | edit | yes | — | — | Set the outgoing transition for a slot or the default. |
| `add_effect` | edit | yes | — | — | Add an effect to a slot. |
| `add_text_overlay` | edit | yes | — | — | Add a text overlay to the cutlist. |
| `add_subtitle` | edit | no | — | — | Add a subtitle track entry (planned). |
| `set_color_grade` | edit | no | — | — | Apply a color grade (planned). |
| `zoom_in` | edit | yes | — | zoom_in | Shorthand for adding a zoom_punch_in effect. |
| `apply_filter` | edit | yes | — | — | Apply a named filter to a slot. |
| `reorder_slots` | edit | no | — | — | Reorder slots in the cutlist (planned). |
| `remove_overlay` | edit | no | — | — | Remove an overlay by id (planned). |
| `change_tempo` | edit | yes | — | — | Request a tempo change (currently falls back to explanation). |
| `zoom_punch_in` | effect | yes | — | — | Scale punch-in effect. |
| `focus_pull` | effect | yes | — | — | Blur focus pull. |
| `freeze_frame` | effect | yes | — | — | Hold a single frame. |
| `speed_ramp` | effect | yes | — | — | Variable speed segment. |
| `shake` | effect | yes | — | shake | Camera shake. |
| `glitch` | effect | yes | — | glitch | Digital glitch. |
| `vignette` | effect | yes | — | vignette | Edge darkening. |
| `film_grain` | effect | yes | — | film_grain | Film grain texture. |
| `color_pop` | effect | yes | — | color_pop | Saturation boost. |
| `chromatic_aberration` | effect | yes | — | chromatic_aberration | RGB split distortion. |
| `hm_mvgd_hm` | effect | yes | — | hm_mvgd_hm | Heatmap-driven color move. |
| `flash_frame` | effect | yes | — | flash_frame | Single frame flash. |
| `reframe` | effect | yes | — | — | Aspect-ratio reframe. |
| `stabilize` | effect | yes | — | — | Motion stabilization. |
| `text_kinetic` | effect | yes | — | text_kinetic | Animated kinetic text. |
| `lower_third` | effect | yes | — | lower_third | Lower third graphic. |
| `callout_arrow` | effect | yes | — | — | Arrow callout graphic. |
| `whoosh_sfx` | audio | yes | — | — | Whoosh sound effect. |
| `ding_sfx` | audio | yes | — | — | Ding sound effect. |
| `record_scratch_sfx` | audio | yes | — | — | Record scratch sound effect. |
| `camera_motion` | effect | yes | — | — | Preset or keyframe camera move. |
| `depth_push` | effect | yes | depth | depth_push | Depth-aware push-in. |
| `depth_parallax_left` | effect | yes | depth | depth_parallax_left | Depth-aware parallax left. |
| `depth_parallax_right` | effect | yes | depth | depth_parallax_right | Depth-aware parallax right. |
| `world_text` | effect | yes | depth | world_text | Text placed in world-space behind subject. |
| `zoom_out` | camera | yes | — | zoom_out | Pull back; releases tension slightly. |
| `pan_left` | camera | yes | — | pan_left | Horizontal camera pan left. |
| `pan_right` | camera | yes | — | pan_right | Horizontal camera pan right. |
| `hard_cut` | transition | yes | — | hard_cut | Instant cut; attention reset. |
| `fade` | transition | yes | — | fade | Fade; lowers arousal and tension. |
| `dissolve` | transition | yes | — | dissolve | Dissolve; gentle release. |
| `riser` | audio | yes | — | riser | Rising sound effect; builds tension. |
| `hit` | audio | yes | — | hit | Percussive hit; punctuates moment. |
