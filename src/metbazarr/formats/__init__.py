"""Output formats. Each is a module with its variable table, writer helpers and
validator."""

from metbazarr.formats import glide

FORMATS = {glide.FORMAT_NAME: glide}

__all__ = ["FORMATS", "glide"]
