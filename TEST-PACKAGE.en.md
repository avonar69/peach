---
kind: howto
---

# Peach custom test build

## RSS history and completed-download import

Under **Manage following → RSS downloads**, set **Keep saved posts** separately for each feed: **Forever**, days, months or years. Posts remain saved when they disappear from the publisher's current feed. Retention runs from the first save, and refreshing a post does not extend its age. Expiry removes saved post content while preserving minimal duplicate-prevention records; downloaded media stays intact. Repeated IDs or article URLs merge links and previews into one post. Saved images and downloads are URLs served by their original hosts.

Debrid progress appears in the same collapsible task popup as scan progress and stays visible across page navigation. Server-folder downloads show transferred bytes and can be cancelled. Direct browser downloads remain browser-managed. **Show download progress** on the RSS page reopens recent tasks.

In **Peach configuration → Download providers**, each debrid provider has **Scan and import after download**. Select a folder inside a media library configured in **Libraries & import**; Docker paths must refer to the same mounted container folder. The default is off. When enabled for a download, its completed video is registered and processed as a single-file task, including the existing filename, preview, metadata and StashDB options. A busy library scan defers import. Import failure keeps the completed file; **Retry import** processes it again without downloading it again. Cancelling an import also keeps the file.

## Updating an existing media library

Use **Data management → Scanning and acquisition → Scan All (Find new)**, the default action. Directory discovery lists all files, but only newly registered videos enter media probing, missing-preview generation, metadata and StashDB matching. A scan with no added videos finishes after discovery. The completed message reports how many new videos were processed.

Choose **Scan All (Fresh)** from the dropdown and confirm when you want all registered videos considered. This preserves metadata, installed pictures and history, and reuses usable previews. Use the existing preview, metadata or failed-item actions for those specific tasks. StashDB's failed-search skip option is independent of the scan scope and continues to apply within it.

## Actor profiles and resync

Open an actor page to see career dates, birthdate and current age, height, measurements, breast type, nationality, ethnicity and eye/hair colors on the right. **Edit actor info** saves local corrections; **Use synced info** returns all fields to their source values. Sync preserves your corrections and installed pictures.

In **Peach configuration → Sources & subscriptions → StashDB**, use **Resync Actors** to refresh your existing actors, or **Resync Studios** for existing studios. These actions bypass ordinary caches and never scan media or search scenes. Follow progress, pause/resume or stop in Data management. Actor photos follow the saved actor-photo option; studio sync fills missing logos.

Use **Add alias** to enter `Chloe, Clara Fargo, Larissa`: commas separate aliases and spaces inside names remain intact. StashDB aliases join the same list with a separate source.

## RSS and debrid downloads

**Following → All** includes an RSS updates section with the same thumbnails, previews and debrid actions. **Manage following → RSS downloads** provides an **Automatic updates** switch and **Update interval (hours)** for each source, defaulting to 6 hours; save each interval independently. Supported intervals range from 15 minutes to 7 days. Turning automatic updates off retains posts and **Check feeds now** still refreshes that feed manually.

RSS posts show the title, feed/date/time, a main thumbnail, and every preview thumbnail from the post, followed by download links. Each preview opens its own full image; description prose is hidden. After updating, use **Check feeds now** to populate images for existing posts.

Beside each added RSS source, **Hide unsupported links** saves a filter for that feed. It uses the supported-host lists from configured debrid providers; run **Test connection** in Download providers to load those lists. Turn the filter off to display all links again.

Open **Manage following → RSS downloads**, add a public HTTP/HTTPS RSS/Atom feed, and use **Check feeds now** to fetch new items. Items show their original links, including supported hoster links such as rg.to. Feed refreshes preserve saved items and do not start paid downloads automatically.

In **Peach configuration → Download providers**, save an AllDebrid or Real-Debrid API key, then use **Test connection** to confirm access and load supported hostnames. Click the cloud-download icon beside an RSS link to prepare and start its download with that provider. Single-file links start directly; torrents with multiple files offer a choice after preparation. The prepared direct link also remains available below the item.

For browser downloads, leave **Download folder** blank. For Docker downloads, mount a writable host folder to `/downloads` and enter `/downloads` in the provider settings; the folder must already exist inside the container. A click then queues a server download with progress and cancellation. Partial files remain available for validated resume; cancellation does not remove tasks from the provider account. Completed filenames include a short task identifier to avoid overwriting existing files.

Provider APIs are covered with simulated responses; testing a real subscription and the Docker volume permissions requires your configured account and deployment.

This cumulative revision hides confirmed missing paths after a completed local-library scan, retaining their saved records. Renaming a file therefore leaves only its current path in the active library. Returning a file to its original path restores that record. Unreadable or offline folders are preserved; remote-source cleanup remains in Resource sync. Run a full **Synchronize media library** scan after installing; metadata-only scans do not discover filename changes.

StashDB now has **Skip previously failed or unmatched StashDB searches** and **Only match newly added media**, both initially off. New-media-only begins when enabled and saved; older videos remain available for manual preview. Turn it off to include older videos. Failed-search skipping persists while matching hints/options stay unchanged, including successful searches with no candidates. Turn it off to retry failures. Source-wide rate limits still use cooldowns. Manual preview always permits a fresh search. The repair confirmation uses translated text throughout.

This cumulative revision adds cached pending StashDB reviews, a one-day cache for successful searches with no results, and StashDB counts in Data management → Manual review. Unchanged completed scenes remain skipped. Failed searches or image installations remain retryable. Manual preview searches again on request.

Under Sources & subscriptions → StashDB, use **Ignore filename text when matching** for literal characters, words or phrases, one per line. For example, enter `!` to remove exclamation marks from matching hints. Matching ignores case; filenames and saved metadata stay unchanged. **Minimum automatic match confidence (%)** accepts 50–100, defaults to 85, and keeps the unique-result and conflicting-detail checks. Save these options before scanning.

Based on Peach 0.46.1. This is a local test build, not an upstream release.

This revision fixes StashDB library searching and installs images in Peach's displayed image folders. Starting a metadata scan or applying a match recovers StashDB images cached by earlier test builds, without replacing current pictures. Exit Peach before replacing the portable `app` folder; keep `peach-data`.

In Configuration → Sources & subscriptions → StashDB, save your options and use **Run metadata scan with StashDB**. This starts Peach's metadata scan, including enabled metadata sources. Follow progress in Data management; completion lists StashDB applied, review and already-up-to-date counts separately from release-code identification. Open **Review → StashDB matches** (or follow the link from source settings) for queued results and manual scene/actor search. Select a library item, preview matches, then apply your choice. Dismissing scene matches preserves local metadata and skips automatic review until evidence or options change. **Test connection** shows an explicit success message.

Completed scenes and already installed StashDB actor pictures are skipped. Changed scene evidence, enabled image/cast options or missing installed pictures allow work to run again. Existing actor identities and pictures are preserved during cast corrections. Browser tab titles and Windows tray menus use the interface language; changing it in the main application updates the tray preference. The native tray defaults to English.

## Windows portable

Extract the whole ZIP, then double-click `Start-Peach.cmd`. It starts the tray application and opens the browser. Complete first-time setup on that computer using the localhost address it opens. No Python, Node, installer or administrator account is required. FFmpeg, FFprobe, untrunc and cloudflared are included, with their original license notices and media-tool source archives.

The launcher keeps application data in `peach-data` beside itself. Keep the extracted folder together. Exit Peach from its tray menu when finished. Launch with this script each time; running the executable directly uses Peach's normal desktop data location.

To update an existing portable test installation, exit Peach first, replace its `app` folder with the `app` folder from this archive, and keep your existing `peach-data` folder. Then run `Start-Peach.cmd` again. Reload an already-open browser tab so it loads the updated interface.

Use a separate empty test media folder first. Scanning reads filenames and writes the test database. Peach also has explicit file organization and deletion features; these perform the actions selected in their own dialogs.

## Interface languages

English is the default. Choose English, Simplified Chinese, Traditional Chinese, Spanish, French, German, Brazilian Portuguese, Japanese, Korean or Vietnamese at the top of setup/login, or under Application & maintenance in Configuration. The choice is stored per browser and origin. Changing it reloads the page, so save pending edits first.

The catalogs cover 3,937 audited public-source text candidates, including backend scan stages, orientation filters, library health and source diagnostics. Static text, parameterized text and imperative HTML use the same catalog. Animated counters are translated before they are split into characters. Actor names, filenames, editable values and marked media titles keep their original text. Unknown external messages retain their source language.

Generated translations use the public upstream revision and generic authored interface labels. English includes manual terminology overrides; the additional languages are machine-generated and may need wording refinements. Missing custom wording falls back to English. Translation runs locally from bundled files; using Peach does not contact a translation service. Run `npm run check:i18n --prefix frontend` in a source checkout to verify all catalogs' audited coverage and template parameters. The inventory is in `frontend/src/i18n/inventory.json`, and curated English wording is in `en.json`.

## Fullscreen on ultrawide monitors

Open the video player's gear menu → Fullscreen sizing:

- **Fit to screen** is the default. It preserves the whole frame and aspect ratio, with black bars where needed.
- **Original resolution** preserves aspect ratio and avoids enlarging the source video; oversized videos shrink to fit.
- **Fill screen (crop)** fills the display and crops edges to match its aspect ratio.

The selection is saved per browser/origin and applies to new players. It affects fullscreen display size, not the selected stream quality. The controls are tested in Chrome at 5120×1440, including preference persistence across reloads.

## Seeking, shortcuts and wheel volume

Open Settings → Browsing & playback → Seek controls. Each action has its own duration (1–3600 seconds) and keyboard shortcut:

| Action | Default key | Default duration |
| --- | --- | --- |
| Big fast forward | Up arrow | 60 seconds |
| Big rewind | Down arrow | 60 seconds |
| Small fast forward | Right arrow | 10 seconds |
| Small rewind | Left arrow | 10 seconds |

Existing small-jump durations are retained when upgrading. Click a shortcut field and press your preferred key combination. Duplicate bindings are rejected. Reset seek shortcuts restores the four default keys while keeping your chosen durations. Text fields, menus, sliders and settings keep their normal keyboard controls. Small-jump amounts also apply to miniplayer buttons, system media controls and immersion double taps.

Enable **Mouse wheel changes volume over video** to adjust volume by five percentage points per wheel event. It starts off. With the option off, the page scrolls normally. Volume stays between 0% and 100%; controls and menus keep their scrolling behavior. These preferences are saved in your browser for the current origin.

## StashDB scene and actor metadata

Open Configuration → Sources & subscriptions → StashDB. Enter your own API key, save, and test the connection. [StashDB's account and API-key guide](https://guidelines.stashdb.org/docs/faq_getting-started/stashdb/accessing-stashdb/) explains how to obtain it. The key is stored only on the Peach server; the browser shows whether a key is saved.

With scene pictures disabled, automatic StashDB scans only match existing actors and studios, once per identity; completed lookups and installed photos are reused. Scene searches and scene-based cast correction require scene pictures to be enabled. Actor photos have their own switch. Manual scene preview remains available in Review.

Stop an active or paused scan with **Stop scan** in Data management or the scan popup. Completed work is retained; the current request finishes or times out before the scan stops. To continue scanning later, start a new scan. Pause and Resume temporarily suspend the same task instead.

Filename matching in Libraries & import reads actor and studio names locally. StashDB cast correction uses a matched scene to correct filename-based actors, while manual assignments stay intact.

Matching combines title, date, studio/parent studio, actors and aliases, and duration. It can find dated studio/actor filenames without knowing the scene title. A filename by itself is not treated as proof. Automatic application requires a strong, unique result supported by multiple signals. Conflicts, ties, approximate dates and truncated searches stay for review. **Review matches from metadata scans** opens queued scene results.

Cast corrections replace filename and earlier StashDB assignments while retaining other manual assignments. Manual scene choices are recorded as reviewed; automatic matching preserves fields protected by manual edits or review. Actor identities use StashDB IDs and disambiguation. Automatic image collection fills missing pictures; manual review can replace pictures according to your selected options. Files are not renamed.

Peach uses the read-only API, paced requests and the server's Retry-After cooldown. It does not submit edits, votes, fingerprints or images to StashDB. API keys are never sent with image downloads. No key is bundled: the adapter has been tested with a simulated API and synthetic images; live authenticated matching must be tested with your account.

## Optional actors and studios from filenames

Open Configuration → Libraries & import → Filename matching. **Automatically match actors** and **Automatically match studios** are separate switches, both off by default. Enable the ones you want, then rescan to apply them to existing files. Switching off stops future matching and keeps existing links.

Your naming convention is supported directly:

```text
StudioName.26.10.22.Naomi.Lastname.And.Aubree.Blair.mp4
```

With actor matching enabled, scanning adds and attaches **Naomi Lastname** and **Aubree Blair**. With studio matching enabled, it also adds **StudioName**. Four-digit years work too. Common quality suffixes such as `.1080p.WEB-DL.x264` are ignored. Each actor in this convention must have two to five name words. Use it when the part after the date contains actor names; arbitrary scene titles cannot be distinguished reliably from names.

For `EvilAngel.26.10.22.Jane.Doe.mp4`, studio matching reads `EvilAngel` before the date. A unique existing studio name or alias is reused (spaces and letter case are normalized); otherwise a studio is created from that prefix. Ambiguous studios, invalid dates and conflicts with existing attribution are skipped. Manual and reviewed studio fields remain protected. Studio links and their compatibility field use the separate `scan:filename-studio` source. A rescan updates only this source's links.

For other naming conventions, use an explicit field:

```text
Scene title [actors=Naomi Lastname; Aubree Blair].mp4
```

Plain filenames also match uniquely known actor names/aliases with word boundaries; dots and underscores act as spaces. Ambiguous aliases and partial matches are skipped. New actors do not need an online lookup. Full scans and file-push ingestion use the same behavior. Rescan an existing library to apply matching to its files. Generated links use the independent `scan:filename-actors` source; rebuilding them preserves links from manual edits and other sources. Media filenames are not renamed.

## LAN access over HTTP

During setup, expand Advanced settings and select Devices on the local network. For an existing Windows setup, open Configuration → Network & access, enable Allow connections from the local network, and save. Disabling it restores localhost-only listening. Windows may prompt for access on private networks; Peach does not change firewall rules for you.

From another device, open `http://<server-IP>:8900` (or your configured port). The UUID compatibility implementation uses `crypto.getRandomValues()` and works on ordinary LAN HTTP. Authentication and HTTPS behavior are retained. Desktop first-time setup remains local to the server computer. Set an access password when allowing other devices.

## Docker / Linux

Use the separate source ZIP; the Windows executable does not run in Linux containers. The source ZIP includes rebuilt browser bundles, so Docker needs no frontend build step.

1. Extract the source ZIP and open a terminal in its `peach` folder.
2. Copy `compose.test.env.example` to `.env` and set `PEACH_MEDIA_ROOT` to an existing host media folder. Set `PEACH_BIND=0.0.0.0` to publish to your LAN, or keep `127.0.0.1` for local access. Choose another `PEACH_PORT` if 8900 is already occupied.
3. Run `docker compose -f compose.test.yaml up -d --build`.
4. Open `http://localhost:8900` on the server or `http://<server-IP>:8900` from your LAN. Configure the media path as `/media` inside Peach.

This compose file uses image `peach-custom:test`, a separate `peach-test-data` volume, and a read-only media mount. It does not include a GPU override; carry over the GPU device reservations from your existing deployment if needed. No Docker image has been built or run on the build machine because its Docker daemon was unavailable.

Stop the test with `docker compose -f compose.test.yaml down`. Keep the volume if you want to retain test data.

## Source and reproduction

The companion source ZIP includes the application, rebuilt browser bundles, tests, locked dependencies, this guide and the upstream AGPL license. See `BUILD-INFO.json` for the base commit and test-build identity.

For a Windows rebuild, install Python 3.14, uv and Node 24+, synchronize the locked dependencies with the build extra, and use the existing `scripts/build_windows.ps1 -Standalone` entry point. Its media-tool arguments require the included tool manifests plus their corresponding source archives. The upstream build script validates their hashes.

Automatic updates are off by default. Keep them off during testing so an upstream update does not replace this custom build.
