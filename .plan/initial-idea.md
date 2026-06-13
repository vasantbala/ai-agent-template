# AI Agent Template

## Goal

A reusable, forkable template for building AI agents that can be configured or extended without major refactoring. The template should lower the activation energy for standing up a new agent from scratch.

## Core Capabilities

- **MCP server integration** — plug in one or more Model Context Protocol servers to give the agent tools and context sources
- **Task reasoning** — the agent reasons over its inputs to derive and execute a sequence of tasks autonomously
- **Multi-agent support** — optionally connect to another agent (parent or child) for delegation or orchestration
- **Observability** — Langfuse-based tracing and logging out of the box
- **Evals** — built-in evaluation hooks to measure and track agent quality over time

## Design Principles

- Configuration-first: change behavior through config, not code
- Extension points over rewrites: override or compose, never gut
- Batteries included for observability and evals from day one