# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html). Versions
are derived from git tags via `hatch-vcs`.

## [Unreleased]

### Added
- Project-tree audit: `audit_tree()` with `ProjectReport` / `FileReport`.
- `XschemCLI` expansion: `netlist_text()`, buffered `session()`, partial-failure
  detection (raises `RuntimeError` on `IS MISSING` placeholders or Tcl errors),
  and a configurable hard subprocess `timeout` (default 120 s).
- Subcircuit authoring: `set_subcircuit_metadata()`, `subcircuit_ports()`,
  `SubcircuitPort`.
- Bill-of-materials: `Schematic.bom()` with `BomEntry` (hierarchy roll-up via
  `flatten=`).
- Refactoring helpers: `transform_components()`, `set_component_attributes()`,
  `bulk_update()`.
- Pin-side classification: `Schematic.pin_side()`, `Symbol.pin_side()`,
  `geometry.pin_side` (honours rotation/mirror).
- Net connectivity: `NetAnalyzer`, `connectivity_from_schematic()`,
  `connectivity_from_netlist()`.
- Schematic diffing: `diff_schematics()` with `SchemDiff` /
  `ComponentChange` / `NetChange` / `TextChange`.
- Header K-block accessors; `Symbol` delegates K-block parsing.

### Changed
- Hardened `XschemCLI` controls (env isolation, `no_rcload`, `rcfile`, `cwd`).

### Fixed
- Serializer, library resolution, validator, and connectivity correctness fixes.

### Internal
- Added pyright type-checking (CI + dev dep), a coverage floor (`fail_under = 90`),
  `.gitattributes` LF enforcement, a wheel import smoke test in the publish
  pipeline, and SHA-pinned the PyPI publish action.

## [0.1.0] - 2026-03-22

### Added
- Initial release: `.sch`/`.sym` parsing and round-trip-faithful serialization,
  schematic query/edit/generate APIs, symbol and library resolution, hierarchy
  traversal, pin geometry, validation, attribute codec, and the `XschemCLI`
  wrapper.

[Unreleased]: https://github.com/Cognitohazard/pyxschem/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Cognitohazard/pyxschem/releases/tag/v0.1.0
