# Changelog

All notable changes to this project will be documented in this file.

## [0.9.0] - 2026-02-24
### Added
- **Initial Public Release** of the ODL (Organizational Definition Language) compiler.
- **Core Compiler Pipeline**: Implementation of the full transformation sequence: `Parse -> Syntax Check -> Expand -> Resolve -> Wiring Check -> Assemble`.
- **Syntactic Sugar Expansion**: Support for high-level organizational constructs:
    - `generate_team`: Self-correcting feedback loops.
    - `approval_gate`: Human-in-the-loop checkpoints.
    - `ensemble`: Diversified parallel generation and consolidation.
    - `fan_out`: Dynamic iteration based on data sources.
- **Deterministic Path Generation**: Implementation of structural `stack_path` calculation to ensure consistent identity across compilations.
- **Scope Resolution Engine**: Logic for resolving logical artifact names to physical IDs with support for ancestor and sibling visibility.
- **Validation Rules**:
    - Static syntax validation for OpCode requirements and naming conventions.
    - Wiring validation to detect circular dependencies and undefined references.
- **Standard IR Assembly**: Pydantic-based Intermediate Representation (IR) generation for consumption by the ODL Kernel.