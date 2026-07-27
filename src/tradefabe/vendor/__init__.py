"""Vendored third-party code, pinned to upstream commits. See README.md.

Deliberately empty of imports: `kronos_model` pulls in torch, and importing that eagerly
would make `import tradefabe.vendor` cost ~2s and fail outright without the [kronos] extra.
"""
