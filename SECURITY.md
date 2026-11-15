# PDFManipulator security policy

PDFManipulator is a local-first PDF editor with an optional ChatGPT connection.

## What stays local

PDF bytes, filenames, thumbnail generation, page editing, output PDFs, saved
workflow recipes, and local OAuth token storage remain on the user's computer.

When a user explicitly enables an AI provider, the interpreter sends **only**
instruction text and generic input labels such as `input1`, not PDF contents.
The model output is a restricted workflow plan that must pass local validation
before a user can review and export it. Do not treat model responses as code.

ChatGPT browser authentication uses OAuth authorization, state/nonce/PKCE,
identity-token verification, and Windows DPAPI encryption of stored sessions.
The app does not solicit or persist a ChatGPT password. Cloud AI requests
remain subject to account eligibility, provider rules, consent, and limits.

The optional MCP server is local stdio only and requires an explicit folder
root. The project does not include a public unauthenticated MCP endpoint.

## Responsible disclosure

Please report suspected vulnerabilities using **GitHub's private security
advisory / private vulnerability reporting feature** on this repository,
where available. Avoid posting exploit details or sensitive document examples
in public issues. If private reporting is unavailable, open a general public
issue requesting a secure reporting channel without disclosing exploit details.

## Public repository rules

Never commit:

- API keys, OAuth access/refresh tokens, passwords, session files, private keys,
  `.env` files, or other credentials
- Sensitive PDFs, scans, personal documents, or rendered output files
- Virtual environments, local configuration stores, build directories,
  or compiled executables containing unnecessary private metadata

Ignore patterns in `.gitignore` block these common file types, but do not
replace a local review. Check staged files and Git history before making a
repository public. If credentials ever reach Git history, revoke and rotate
them; removing a file in a later commit is not enough.

## Scope

Automated tests and source-level audits cannot certify that a program has
no vulnerabilities. Review authentication and file-handling changes before
distribution and test real user consent flows separately.
