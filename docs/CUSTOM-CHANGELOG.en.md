---
kind: changelog
---

# English-first interface, StashDB and playback changes

- **Offline interface languages:** English is the default, with nine additional languages available from setup or settings. All catalogs are bundled locally, so normal use does not contact a translation service.

- **Complete interface translations:** Localizes menus, onboarding, settings, browser titles, Windows tray menus, diagnostics and management pages. Dynamic scan actions, estimate units/scopes and unavailable diagnostic counts are translated before filenames and numbers are inserted.

- **LAN and ordinary HTTP access:** Adds an explicit option to accept connections outside localhost. A UUID fallback keeps the frontend working on ordinary LAN HTTP addresses where crypto.randomUUID() is unavailable.

- **Actors from filenames:** Optionally matches known actor names and aliases, or creates actors from supported dated filenames and explicit actor fields. The switch is independent of studio matching and starts disabled.

- **Studios from filenames:** Optionally matches or creates a studio from the filename prefix before the release date. Unique existing names and aliases are reused while ambiguous identities and protected assignments remain unchanged.

- **StashDB source configuration:** Adds API-key setup, explicit connection-test feedback and scan initiation under Sources & subscriptions. Requests use the read-only GraphQL API with pacing, bounded results and server-directed cooldowns.

- **Multi-signal scene matching:** Combines studio, release date, actor names/aliases, title and duration instead of relying on the full filename. Ambiguous, conflicting or truncated searches remain available for manual review.

- **Filename ignores and match confidence:** Adds literal characters, words or phrases to ignore when deriving filename hints, without renaming files. The automatic-match threshold is adjustable from 50–100%, while uniqueness and conflicting-detail checks remain required.

- **Actor photos, scene pictures and cast correction:** Provides separate settings for actor photos, scene pictures and scene cast corrections. Existing actor identities and pictures are preserved, and unrelated manual assignments remain protected.

- **Picture installation and recovery:** Installs StashDB images in the folders served by Peach's picture endpoints. Earlier custom-build downloads can be copied into missing destinations safely, without overwriting installed pictures or removing the original cache.

- **Incremental StashDB matching:** Skips unchanged completed scenes and installed StashDB actor photos, and reuses known actor identities and pending review results. Successful searches with no candidates are cached for one day to avoid repeated requests.

- **Failed-search and new-media policies:** Adds optional skipping of failed/unmatched StashDB searches and matching only media registered after the setting is enabled. Both options start disabled, and manual preview can still request a fresh search.

- **Unified manual review:** Places queued StashDB results and manual scene/actor searches in Review with apply and dismiss actions. StashDB candidates contribute to Data management's Manual review count and update after decisions.

- **Missing and renamed local files:** Completed local scans hide confirmed missing paths from active browsing and processing while retaining their saved records. Unreadable/offline roots are protected, and files returning to their original paths restore their records.

- **Ultrawide fullscreen sizing:** Adds saved fit-to-screen, original-resolution and fill/crop choices to the player. Fit and original-resolution modes preserve the video's aspect ratio on ultrawide displays.

- **Seek shortcuts and wheel volume:** Separates big/small forward and rewind durations with a customizable shortcut for each action; defaults use Up/Down for big jumps and Right/Left for small jumps. Optional mouse-wheel volume applies over the video while preserving menu and control scrolling.

- **Portable and Docker test resources:** Bundles offline language catalogs and required scraper resources in portable builds. Includes a Docker test recipe, safe environment example, bilingual README links and upgrade instructions.

## Scan behavior

**Stop scan and actor/studio-only matching:** Stop an active or paused scan from Data management or its popup while keeping completed work. Disabling scene pictures limits automatic StashDB requests to unique existing actors and studios, with completed identities reused across scans.

Full sync enumerates configured files and reuses valid existing previews; missing or invalid previews are generated as needed. **Only scan files** registers files and probes missing measurements without generating previews or scraping metadata. Metadata-only skips file discovery. New-media-only limits StashDB matching; folder enumeration remains necessary.

## Verification limits

Authenticated StashDB tests use simulated responses and temporary libraries. Docker image execution, GPU playback and a second physical LAN client were not verified; additional-language wording is machine translated with selected manual corrections.
