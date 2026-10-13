# Tall Order Works previews

Homepage concepts for outreach prospects, published at `https://preview.tallorderworks.com/<slug>/`.
The evening outreach build adds one folder per prospect; a GitHub Action does the rest.

## Folder layout

```
prospects/<slug>/
  prospect.json      what the build needs (see prospects/_example/prospect.json)
  mockup.html        the redesigned homepage, one self contained responsive file (mockups only)
  img/               the prospect's own photos, downloaded by the Action from prospect.json "images"
  out/               written by the Action, never by hand
    build.json       result of the last build and its checks
    desktop.jpg      full page concept at 1440 px
    desktop-top.jpg  first screen of the concept at 1440 px
    phone.jpg        full page concept at 390 px
    current-desktop.jpg   their current homepage, first screen
    email-compare.jpg     current homepage next to the concept, 1200 px wide, for the first email
    current-phone.jpg     (audits only) their current homepage on a phone
```

Slugs are short, lowercase, letters, digits and dashes (for example `premier-ac`). Folders starting with `_` are ignored.

## prospect.json

| Field | Notes |
|---|---|
| business | Their business name as they write it |
| type | `mockup` or `audit` (audit only renders `out/current-phone.jpg`; nothing is published) |
| published | `true` to publish the preview page (mockups only) |
| site_url | Their current homepage URL |
| domain | Their domain, for example `example.com` |
| intro | Optional. Overrides the default intro paragraph on the preview page ({{BUSINESS}} is filled in). Leave it out for new prospects |
| sources_phrase | Used in the footer disclaimer: "using photos and details from ..." (usually the domain) |
| images | `{ "file-name.jpg": "full image URL on THEIR site" }`. The mockup references them as `img/<file-name>` |
| changes | Exactly three `{ "title": "...", "text": "..." }` items shown under "What we changed" |

## What happens on push

1. Push a new or changed `prospects/<slug>/` to `main`.
2. The **Build previews** Action (2 to 5 minutes) downloads the images, renders the screenshots, writes `out/build.json`, commits `img/` and `out/` back to `main` with the message "Build output [skip ci]", and republishes the whole site to GitHub Pages.
3. `git pull` until `prospects/<slug>/out/build.json` has a `rendered_at` later than your push.

Only prospects whose `prospect.json` or `mockup.html` changed since their last build are rebuilt. To rebuild everything, run the Action by hand with "Rebuild every prospect" ticked.

## build.json

| Field | Meaning |
|---|---|
| rendered_at | When the build finished (UTC) |
| source_commit | The commit that was built |
| image_errors | Images in prospect.json that could not be downloaded (fix the URL or drop the image) |
| broken_images_in_mockup | `img` tags in mockup.html that did not load |
| phone_horizontal_scroll | `true` means the mockup scrolls sideways at 390 px. Fix it |
| copy_warnings | Lines in the mockup with hyphens or dashes (phone numbers are allowed) |
| errors | Anything else that failed |
| preview_url | The published preview page (mockups only) |

## Links used by the outreach emails

* Preview page: `https://preview.tallorderworks.com/<slug>/`
* Full concept on its own: `https://preview.tallorderworks.com/<slug>/concept/`
* Email image: `https://raw.githubusercontent.com/tallorderworks/tallorderworks-previews/main/prospects/<slug>/out/email-compare.jpg`

## Taking a preview down

Delete `prospects/<slug>/`, commit "Take down <slug>", push. The next publish removes the page (about 2 minutes).

## Rules for mockups

* Their real name, phone, address, hours, services and photos. Never invented reviews, stats or awards.
* No Tall Order Works branding inside mockup.html (the preview page around it carries ours).
* No hyphens or dashes in the copy; phone numbers are the only exception.
* Must look right at 1440 px and at 390 px with no sideways scroll.
* One Google Fonts link is fine; everything else inline.
