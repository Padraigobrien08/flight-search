# Acceptance tests (locked)

These tests are the definition of done for the features in `/features.json`.
They were written before the features exist, and they fix the interfaces.
Claude Code sessions cannot edit this directory (a PreToolUse hook blocks it);
only a human changes them. Imports live inside each test so one missing module
doesn't break the others.
