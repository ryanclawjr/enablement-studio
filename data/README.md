# Local database

`enablement.db` is created in this directory on first run. The file is
gitignored. `schema.sql` is the checked-in v0 schema applied by the
store package.

The public Cloudflare host does not use this file. Visitor pastes live in a
per-session ephemeral sqlite, not a shared guestbook.
