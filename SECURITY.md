# Security Policy

## Supported versions

| Version | Supported |
|---------|-----------|
| `main`  | ✅ Latest commit |
| Older tags | ❌ No backports |

## Reporting a vulnerability

**Please do not open a public GitHub issue for security vulnerabilities.**

Report security issues privately via GitHub's
[Security Advisories](https://github.com/M-vdBerg/GraphRAG/security/advisories/new)
feature (Repository → Security → Advisories → New draft advisory).

Include:
- A description of the vulnerability and its potential impact
- Steps to reproduce or a proof-of-concept
- Any suggested mitigations you are aware of

You can expect an acknowledgement within **72 hours** and a resolution
timeline within **14 days** for critical issues.

## Scope

Issues in scope:
- SQL / Cypher injection via MCP tool inputs
- Authentication or authorisation bypasses in the MCP server
- Container escape or privilege escalation via the Docker setup
- Credential leakage (e.g. secrets ending up in logs or image layers)

Out of scope:
- Vulnerabilities in upstream dependencies (report those to the respective
  project maintainers)
- Issues that require physical access to the host machine

## Security design notes

- All containers run as a non-root user (`appuser`, UID 1001)
- No secrets are committed to the repository — credentials are loaded
  exclusively from environment variables / `.env` (gitignored)
- The `internal` Docker network isolates PostgreSQL and the watcher from
  external access; only the MCP server is on the `external` network
- MCP tool inputs are validated via Pydantic before reaching the database
