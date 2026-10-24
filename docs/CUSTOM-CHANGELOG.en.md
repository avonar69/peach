---
kind: changelog
---

# English-first interface, StashDB and playback changes

- **Interface languages:** English by default, with Simplified/Traditional Chinese, Spanish, French, German, Brazilian Portuguese, Japanese, Korean and Vietnamese available offline.
- **Complete interface text:** Localizes menus, settings, onboarding, browser titles, Windows tray menus, scan popups, diagnostics, Taste, Organize, Task center and repair confirmations. Dynamic action labels, estimate units/scopes and unavailable diagnostic counts are translated before values are inserted.
- **LAN access:** Adds an explicit network-access option and a random UUID fallback for ordinary HTTP origins where browsers do not expose `crypto.randomUUID()`.
- **Filename actors:** Optional matching and creation of actors from known names/aliases and supported dated filenames or explicit actor fields.
- **Filename studios:** Independently optional studio matching/creation from the prefix before a filename's release date.
- **StashDB source:** Adds API-key setup and connection feedback under Sources & subscriptions, using read-only GraphQL queries and paced requests with cooldowns.
- **Scene matching:** Combines studio, date, actors/aliases, title and duration; ambiguous, conflicting or truncated results require review.
- **Matching controls:** Adds literal filename-ignore rules and a configurable 50–100% automatic-match threshold, retaining uniqueness and conflicting-detail checks.
- **Images and cast:** Separate actor-photo, scene-picture and cast-correction settings; preserves manual assignments and existing actor identities/pictures. Images install in Peach's displayed folders and earlier custom-build downloads can be recovered safely.
- **Incremental matching:** Skips unchanged completed scenes and installed actor pictures, reuses known actor identities and pending reviews, and caches successful empty searches for a day.
- **Scan policy:** Optional skipping of failed/unmatched StashDB searches and matching only media added after enabling the setting. Manual previews remain available.
- **Unified review:** StashDB candidates and manual scene/actor searches share Review; candidates appear in Data management's Manual review counts and support apply/dismiss.
- **Local library reconciliation:** Full local scans hide confirmed missing paths while preserving records, preventing renamed old paths from remaining active. Unreadable/offline roots remain protected; returning files restore their records.
- **Fullscreen sizing:** Saved fit-to-screen, original-resolution and crop choices preserve the intended aspect ratio on ultrawide monitors.
- **Seeking:** Separate big/small forward and rewind durations with customizable shortcuts; defaults use Up/Down for big jumps and Right/Left for small jumps.
- **Wheel volume:** Optional volume adjustment while the pointer is over the video, preserving menu and control scrolling.
- **Portable packaging:** Bundles offline catalogs and scraper resources in Windows builds, with a source/Docker test recipe and upgrade instructions.

## Scan behavior

Full sync enumerates all configured files and refreshes registration. Valid existing previews are reused; missing/invalid previews are generated as needed. **Only scan files** is the quickest discovery mode: it registers files and probes missing measurements, without generating previews or scraping metadata. **Metadata-only** skips file discovery. New-media-only is a StashDB matching policy, not a filesystem watcher or a shortcut around directory enumeration.

## Verification limits

Automated tests use temporary libraries and simulated authenticated StashDB responses. Docker-specific translated status examples are exercised in browser tests; the Docker image itself, GPU playback and a second physical LAN client require deployment testing. Additional-language wording is machine translated with selected manual corrections.
