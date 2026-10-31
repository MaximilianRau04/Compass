# Security

Please do not report security problems in public issues. Use
[GitHub's private reporting](https://github.com/MaximilianRau04/Compass/security/advisories/new) instead,
with the version you run and how to reproduce the problem. This is a personal project, so I answer when
I can and fixes go into the newest commit on `main`, the only supported version.

Compass holds personal data, so when you run it:

- Keep the dashboard behind a VPN or another access control, see `docs/deploy.md`.
- Keep `.env` private. Calendar links carry secret tokens, and so do the values of `.env`.
- Treat the MCP login like the dashboard login: it gives an AI assistant access to your data.
