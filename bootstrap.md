# Etree Tag configuration bootstrap

## Current behavior at `ba4c812`

- [cli.py](cli.py) is the normal entry point. It takes explicit show folders or a parent directory, plus optional overrides for the config path, SQLite database, log file and tag clearing. Without a show folder or parent argument, folder selection fails. It configures logging before loading TOML and opens SQLite before gathering folders.
- The CLI defaults to the checked-in [config.toml](config.toml), `db/etree_scrape.db` and `log/tag_log.log`. Tag clearing is off unless requested. There is no first-run setup, saved user config, or config schema version.
- [services/config.py](services/config.py) loads TOML into an `AppConfig` dataclass with preferences, album formatting, cover settings, recording-folder aliases and support-file paths. It supplies defaults and normalizes some values. It has no schema-version check or comprehensive validation.
- Artwork libraries and default images are mapped by artist abbreviation. The shipped configuration includes Grateful Dead libraries and a bundled fallback. Some external tool defaults point to Windows paths specific to one machine.

## First release

Make first-run configuration the first implementation priority. Keep the checked-in TOML intact as the baseline for shipped defaults. Generate a separate user TOML that applies across shows and later runs. The user should be able to finish setup without editing source code or supplying command-line flags.

1. Start in `cli.py`, before file logging, SQLite initialization or show processing. If no user config exists, launch guided setup in an interactive session. In a noninteractive session, print how to run setup or supply an explicit config.
2. Read the shipped defaults and show the default beside each question. Enter accepts the displayed value. Use the same setting definitions for prompts, loading and validation. Where the shipped baseline has no portable default, ask for a value or allow the user to leave an optional setting unset.
3. Validate the proposed settings, save them to a user-owned TOML with `config_version = 1`, and print the full path and editing instructions. Use a per-user configuration directory so different checkouts can share the file. Choose the exact platform-specific path during implementation.
4. End setup after saving. Setup itself leaves show files untouched. Later launches load and validate the saved preferences. Preserve the explicit `--config` path for users who already maintain their own TOML, including a documented way to adopt older unversioned configs.

### Prompts and defaults

| Preference | First-run default or behavior |
| --- | --- |
| Library or starting folder | Ask for the user's location. There is no portable music-library path. Keep the choice reusable while allowing a different folder for an individual run. |
| Show discovery | Support the current single-show and parent-folder workflows. Explain that parent mode targets immediate subdirectories. |
| Database | Offer the normal SQLite catalog path by default. Allow an alternate path and explain that a fresh catalog is seeded from the bundled CSVs. |
| Replace existing artwork | No. Preserve existing artwork. |
| Back up replaced folder artwork | Yes. Ask when replacement is enabled. |
| Artwork search and fallback | Use the shipped per-artist mappings. For Grateful Dead, search `EE_Artwork` then `TV_Artwork` and use `GD_Art/default.jpg` as the shipped fallback. Allow custom paths where the current tagger supports them. |
| Clear existing FLAC tags | No, matching the current CLI. |
| Album and track formatting | Use the shipped album components, abbreviations and segue marker. Keep detailed formatting in advanced settings or editable TOML. |
| Logging and support tools | Keep routine logging on defaults. Ask about external tools only for features that use them. Machine-specific shipped paths should not block basic tagging. |

Resolve inherited asset paths against the shipped config location so bundled artwork remains available from a per-user TOML. Resolve relative paths supplied by the user against their config file. Keep per-run selection and explicit CLI overrides available.

## Validation and upgrades

Validate the effective configuration every launch, including parse errors, schema version, field types, supported values and relationships such as matching album format list lengths. Check applicable paths before the operation that needs them. Report errors with the file path, the setting and what needs to change, before any writes to recordings.

Use `config_version` for the settings format. App release numbers, file modification times and edits to individual Python files do not trigger setup. A change to a setting should update the shared definition used by both setup and runtime. Start at version 1 and add migrations when an incompatible change arrives.

| Config state | Startup behavior |
| --- | --- |
| Missing | Run interactive setup or explain how to provide a config. |
| Current and valid | Load and continue with the user's saved choices. |
| New optional setting with a safe default | Inherit the shipped default without prompting. |
| Older schema with a mechanical upgrade | Migrate existing choices automatically. |
| Older schema with a choice required | Ask only about the affected settings. Show the previous choice as the default wherever it still applies. |
| Invalid TOML or an unsupported newer schema | Explain the problem and preserve the file for correction or use with a compatible version. |

Validate a migrated config before publishing it. Keep a backup of the prior TOML and write the new one atomically. If the user cancels or migration fails, keep the original available. A later **Change settings** action could reuse the prompt sequence with the user's current values.

## Follow-up candidates

- Add an opt-in tagging preference to expand two-digit years in show folder names, such as `gd74[...]` → `gd1974[...]`. Check the existing folder-year standardization in `RecordingFolder` and the validation and renaming workflow before wiring it into tagging. Keep folder names as-is by default. When the feature is available, explain the rename in bootstrap and save the choice in the user TOML. Existing configs can inherit the off default without prompting. If a tagging preview is added, show the old and proposed paths there. Check for ambiguous years and destination collisions before renaming.
- Re-evaluate artwork behavior against the post-pull code before changing artwork policy. The current options are sufficient for the first bootstrap release. Revisit an explicit **No fallback** choice once the missing-art path is verified end to end.
- Consider a separate read-only tagging preview that enumerates proposed file and metadata changes, identifies artwork and checksum implications, and asks for confirmation before applying the batch. This is a candidate for the tagging workflow. First-run configuration can ship independently.
- Retain the verification, manifest handling, artwork and reporting proposals in [LOCAL_CODE_NOTES.md](LOCAL_CODE_NOTES.md).
