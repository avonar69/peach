---
kind: changelog
---

# English-first interface, StashDB and playback changes

- **RSS archive retention:** Each feed keeps posts forever or for a configured number of days, months or years from first save. Repeated item IDs or article URLs merge download links and previews, while expiry keeps minimal identity records to prevent old posts reappearing.
- **Debrid progress popup:** Reuses the existing collapsible background-task frame and stays visible across pages, showing real server-download byte progress and import status. Cancellation, retry and recent-task reopening are available from the same UI.
- **Import completed downloads:** Each debrid provider can opt into automatic scanning and import for completed videos in a configured library folder. The persistent follow-up processes only that file, waits for active scans, resumes queued work and preserves the download when metadata needs a retry.

- **Incremental library updates:** Data management defaults to Scan All (Find new), processing only videos added during directory discovery. An unchanged library finishes without media probing, preview generation or metadata/StashDB work; explicit Scan All (Fresh) remains in the menu with confirmation and preserves saved data.
- **Reliable new-file detection:** Scan checkpoints record an asset-ID watermark so same-second scans and resumed directory walks retain separate new-file scopes. Completion reports the count of newly processed videos.

- **RSS in Following:** Following → All includes the RSS gallery and its original download/debrid actions. Creator, source, tag and duration filters retain their own scope.
- **Per-feed automatic updates:** Each RSS source has an automatic-update switch and a saved interval, defaulting to 6 hours. Disabling it retains posts and manual refresh; the scheduler checks due feeds without running scene metadata work.

- **Actor profile details:** Shows career dates, birthdate and current age, height, measurements, breast type, nationality, ethnicity and eye/hair colors on the right of actor pages. Edit fields locally or return to synced values; resync preserves manual corrections.
- **Actor aliases:** StashDB aliases sync into Peach's alias list with their source retained. Comma-separated entry adds multiple aliases while preserving spaces inside names such as Clara Fargo.
- **Actor and studio resync:** Separate actions in StashDB settings refresh only existing actors or studios, using bound IDs where available. They bypass ordinary caches, retain manual edits and installed pictures, and support the scan task's pause, resume and stop controls without scene searches.

- **Illustrated RSS posts:** Displays each post's title, feed and publication time, main thumbnail, and all preview thumbnails with their individual full-image links. Description text stays hidden, and image links are kept separate from download links.

- **Per-feed debrid link filtering:** Adds a saved switch beside each RSS feed to hide links unsupported by configured debrid providers. Turning it off restores the full list, and filtered download buttons retain the correct original link targets.

- **RSS download subscriptions:** Adds public HTTP/HTTPS RSS/Atom feeds under Manage following, with new videos and original download links. Updates reuse existing subscription scheduling and deduplicate saved items without requiring release codes.

- **Inline debrid downloads:** Adds AllDebrid and Real-Debrid API-key configuration, connection feedback and supported-host discovery. A debrid icon beside each supported RSS link prepares and starts a download, with file selection for multi-file torrents.

- **Docker download folders and resumable transfers:** Provider settings accept a folder visible inside the container, or use browser downloads when blank. Server transfers provide progress, cancellation, saved remote task identities, validated partial-file resume and protection against overwriting existing files.

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

**Stop scan and actor/studio-only matching:** Stop an active or paused scan from Data management or its popup while keeping completed work; accepted cancellation shows Stopping until the worker exits. Disabling scene pictures limits automatic StashDB requests to unique existing actors and studios, with completed identities reused across scans.

Full sync enumerates configured files and reuses valid existing previews; missing or invalid previews are generated as needed. **Only scan files** registers files and probes missing measurements without generating previews or scraping metadata. Metadata-only skips file discovery. New-media-only limits StashDB matching; folder enumeration remains necessary.

## Verification limits

Authenticated StashDB tests use simulated responses and temporary libraries. Docker image execution, GPU playback and a second physical LAN client were not verified; additional-language wording is machine translated with selected manual corrections.
