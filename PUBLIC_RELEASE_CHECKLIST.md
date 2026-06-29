# Public Release Checklist (Job Application)

Use this checklist before sharing the repository link publicly.

## 1) Secrets and Credentials

- [ ] Confirm `.env` is local-only and not tracked by git.
- [ ] Ensure `.env.example` contains placeholders only.
- [ ] Rotate any key that was ever exposed by mistake.
- [ ] Verify no private keys/certificates are present (`.pem`, `.key`, `.p12`, `.crt`).

## 2) Sensitive Data

- [ ] Remove personal contact details you do not want public.
- [ ] Remove internal account IDs/tokens from docs and code samples.
- [ ] Ensure no real user data, phone numbers, or PII is committed.

## 3) Repo Quality for Recruiters

- [ ] README clearly explains problem, architecture, and local setup.
- [ ] Include concise "For Recruiters" section and key technical highlights.
- [ ] Ensure commands in README run successfully on a clean machine.
- [ ] Keep only relevant project files (avoid noisy local artifacts).

## 4) Final Validation Commands

Run these locally before publishing:

```bash
# Confirm .env is not tracked
git ls-files .env

# Search for common key prefixes and private key blocks
rg -n "AKIA[0-9A-Z]{16}|ASIA[0-9A-Z]{16}|sk-[A-Za-z0-9]{20,}|AIza[0-9A-Za-z\\-_]{35}|-----BEGIN (RSA|EC|OPENSSH|DSA|PRIVATE) KEY-----"

# Search for common sensitive terms
rg -n -i "password|secret|token|api[_-]?key|private|credential"
```

If `git ls-files .env` prints nothing and scans show no real secrets, the repository is generally safe to share.
