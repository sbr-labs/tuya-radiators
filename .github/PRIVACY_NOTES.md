# Privacy hygiene

This repository keeps Tuya **product_ids** (a hardware model identifier
shared by every unit of a given device class — public catalogue data)
but never **device_ids**, local keys, account UIDs, refresh tokens,
customer emails, LAN IPs, MAC addresses, or anything else that
identifies a specific physical install.

## Always use placeholders, never real values

Even when "documenting an example":

| Field | Placeholder to use in source / docs |
| --- | --- |
| Tuya `device_id` | `bfxxxxxxxxxxxxxxxxxxxx` |
| LAN IP | `192.168.1.100` |
| MAC | `00:11:22:33:44:55` |
| Email | `you@example.com` |

## Two layers of defence

### 1. Local pre-commit hook (`.git/hooks/pre-commit`)

Reads `.pii-deny.txt` (gitignored — your personal pattern list) and
refuses to commit any staged file matching one of those patterns.

The hook is intentionally not part of the working tree — when you clone
the repo you have no patterns, no hook, no friction. If you have
PII you care about, drop a `.pii-deny.txt` at the repo root with one
extended-regex pattern per line, then:

```sh
chmod +x .git/hooks/pre-commit
```

Bypass requires `git commit --no-verify` — intentionally non-obvious.

### 2. CI workflow (`.github/workflows/no-personal-info.yml`)

Runs on every push and PR. Greps for AI-attribution markers, common
public-email TLDs, host-path prefixes, Tailscale hosts, and Tuya
device_id shapes. If any are found, CI fails. Catches accidental
bypasses of the local hook.

The CI scan does **not** see your local `.pii-deny.txt` (it's
gitignored). It scans the public-shape patterns that nobody should
ever publish.

## What to do if a leak slips through

1. Replace the leaked value with a placeholder in the affected file(s)
   and commit normally.
2. **History is still public.** Scrub past commits with
   `git filter-branch --tree-filter ... -- --all` plus a
   `git push --force` to overwrite the public branch + tags. Destructive
   — only safe on a brand-new repo with no external clones.
3. Rotate any leaked credential at its source (Tuya developer portal /
   account settings) regardless of whether you scrubbed history.
