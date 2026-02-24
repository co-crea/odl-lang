# ODL (Organizational Definition Language)

<p align="center">
  <strong>The SQL Moment for Organizational Intelligence.</strong><br>
  Declarative Structure for Collaborative Intelligence.
</p>

<p align="center">
  <a href="#license"><img src="https://img.shields.io/badge/License-Apache_2.0-blue.svg" alt="License"></a>
  <img src="https://img.shields.io/badge/Python-3.11+-blue.svg" alt="Python Version">
  <img src="https://img.shields.io/badge/Coverage-100%25-green.svg" alt="Coverage">
  <img src="https://img.shields.io/badge/AI_Generated-Yes-purple.svg" alt="AI Generated Code">
</p>

---

**The SQL Moment for Organizational Intelligence.**

ODL is a declarative language designed to bring the "Infrastructure as Code" paradigm to organizational orchestration. It separates the logical **Structure** of management from the physical **Workers** (AI Agents or Humans), enabling organizations to be version-controlled, replicated, and refactored.

## ⚡ Features

* **Pure & Lightweight:** A pure Python library with zero dependencies on databases or web frameworks.
* **Deterministic Compilation:** Converts YAML-based organizational definitions into a strictly defined Intermediate Representation (IR).
* **Type Safe:** Provides rigorous Pydantic-based type definitions for ODL components.
* **Developer Friendly:** Simple `import odl` API for easy integration into any toolchain.

## 🏗 Architecture

The ODL ecosystem follows a strict separation of concerns to ensure portability and scalability.

* **`odl-lang` (This Repo):** The "Nouns" and "Verbs" of the language. It handles parsing, syntax validation, and compilation into IR. **Licensed under Apache 2.0.**
* **[odl-kernel](https://github.com/co-crea/odl-kernel):** The reference execution engine (The Physics). It executes ODL definitions deterministically without side effects. **Licensed under BSL 1.1.**



## Quick Start

### 1. Installation

```bash
pip install odl-lang
```

### 2. Compile Source to IR

ODL allows you to define complex team structures, such as a managed generation loop with feedback:

```python
import odl

source_yaml = """
generate_team:
  generator: Product_Designer
  validators: [Sustainability_Expert]
  loop: 3
  inputs: [MarketResearch]
  output: ProductDesign
"""

# Compile Source -> IR
ir_root = odl.compile(source_yaml)
print(f"Compiled Root: {ir_root.stack_path}")
```

## 📖 Documentation

* **[VISION.md](./VISION.md):** The Manifesto. Why we need "Organization as Code."
* **[SPEC.md](./SPEC.md):** The Language Specification.
    * **Syntax Reference:** Complete guide to YAML structure, syntactic sugars, and strict typing rules.
    * **OpCode Definitions:** Detailed behaviors of `serial`, `loop`, `fan_out`, `worker`, and more.
    * **Compiler Pipeline:** How the Source is parsed, expanded, and assembled into IR.

> **Note for Implementers:**
> If you are looking for the **Host Runtime Implementation Guide** (how to execute ODL in Python), please refer to the **[odl-kernel Usage Guide](https://github.com/co-crea/odl-kernel/blob/main/USAGE.md)**.

## ⚖️ The Social Contract

ODL is designed as a gift to the next era of humanity. We believe the "Physics of Organization" should be a public utility, much like SQL or HTTP.

* **Sanctuary of Innovation:** This library (`odl-lang`) is completely free for everyone — individuals, startups, and researchers.
* **Open Standard:** We encourage the community to build IDE plugins, alternative execution engines, and visual editors based on the ODL specification.

## 🌹 Dedication

**Dedicated to the memory of Prof. Kazuhisa Seta, and to all researchers who continue to push the boundaries of Knowledge Engineering in his lineage.**

## 📄 License

Copyright (c) 2026 Centillion System, Inc.

* **Licensor:** Centillion System, Inc. (https://centsys.jp/)
* **Contact:** odl@centsys.jp

Licensed under the **Apache License, Version 2.0** (the "License"). You may use this library for any personal or commercial purpose. For the execution engine, please refer to the [odl-kernel license](https://github.com/co-crea/odl-kernel#license).