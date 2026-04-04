"""Compilation pipeline — 6-step LLM compilation with checkpoint/resume."""

from compendium.pipeline.controller import compile_wiki, incremental_update

__all__ = ["compile_wiki", "incremental_update"]
