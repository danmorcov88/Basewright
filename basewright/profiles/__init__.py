"""Loading and schema validation of profiles.

A profile is a directory of declarative files describing one database engine.
The loader validates it against the JSON Schema in ``schema/`` and rejects unknown
keys, so a profile cannot smuggle in behaviour the core does not understand.
"""
