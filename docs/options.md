# Filter and Replace Guide

[Back to README](../readme.md)

This page explains two useful options in plain terms:

- URL filter: remove unwanted links from consideration.
- URL replacement: correct common link text issues before matching.

## URL Filter (Exclude Unwanted Links)

Use this when certain sites keep showing up but are not useful for your real matches.

Add one pattern per line. If a link contains that text anywhere, it gets ignored.

### Good examples

1. `localhost`  
   Ignores local test links like `http://localhost:9999/...`

2. `google.com`  
   Ignores generic search-result links from Google.

3. `bing.com`  
   Ignores Bing search pages.

4. `webcache`  
   Ignores cached-page links that usually are not the source you want.

### How to think about filter text

1. Keep entries simple and specific.
2. Start with obvious noise sites.
3. Add new entries only after you notice repeated bad matches.

### Common mistakes

1. Adding text that is too broad, like `com` or `http`, which can remove almost everything.
2. Adding spaces by accident (` google.com`) which may not behave as expected.
3. Expecting advanced wildcard logic. This is plain text matching.

## URL Replacement (Fix Link Text)

Use this when links are close to correct, but include a repeatable issue you want to fix automatically.

Each rule has two parts:

1. Text to find
2. Text to replace it with

If the “find” text appears inside a link, it gets swapped with the replacement text.

### Good examples

1. Find: `spankbang.party`  
   Replace with: `spankbang.com`  
   Result: `https://spankbang.party/...` becomes `https://spankbang.com/...`

2. Find: `m.example.com`  
   Replace with: `www.example.com`  
   Result: mobile-domain links become desktop-domain links.

3. Find: `/amp/`  
   Replace with: `/`  
   Result: AMP-style links become normal links.

4. Find: `?output=1`  
   Replace with: `` (empty)  
   Result: removes a noisy query piece from the end.

### Common mistakes

1. Using a find text that is too broad, which changes unrelated links.
2. Creating two rules that fight each other.
3. Expecting case-sensitive or advanced pattern behavior; treat it as plain text replacement.

## Recommended Workflow

1. Add a small filter list first (only obvious noise).
2. Add one replacement rule at a time.
3. Re-run and check results.
4. Keep only the rules that clearly improve matches.

[Back to README](../readme.md)
