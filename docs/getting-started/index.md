# Getting Started

`litestar-granian` integrates the Rust-powered [Granian](https://github.com/emmett-framework/granian) HTTP server with [Litestar](https://litestar.dev/) so `litestar run` executes under a supervised Granian worker group while preserving Litestar server lifespans, logging formatters, and CLI conventions.

## Installation

=== "uv"
    ```bash
    uv add litestar-granian
    ```
=== "pip"
    ```bash
    pip install litestar-granian
    ```
=== "pdm"
    ```bash
    pdm add litestar-granian
    ```
=== "poetry"
    ```bash
    poetry add litestar-granian
    ```

## In This Section

| Page | Description |
| --- | --- |
| **[Quickstart](quickstart.md)** | Create a minimal Litestar application with `GranianPlugin` and run it locally with `litestar run`. |
| **[Migration (v0.16)](../migration/v0.16.md)** | Upgrade notes for the unified supervised process model, automatic formatter matching, and deprecated flags. |
| **[Contributing](../contribution-guide.md)** | Local development setup, testing expectations, and release workflow. |
| **[Changelog](../changelog.md)** | Release history for `litestar-granian`. |
