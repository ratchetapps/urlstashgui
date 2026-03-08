# How Filename Matching Works

[Back to README](../readme.md)

This explains, in plain terms, how a scene filename is compared to a page title from your browser history.

## The Basic Idea

Both sides are simplified before comparing:

- Upper/lower case differences are ignored.
- Spaces and symbols are ignored (` `, `-`, `_`, `.`, `(`, `)`, `!`, etc.).
- A trailing `.mp4` is ignored.
- A trailing `-01`, `-02`, `-99` style ending is ignored only when it is a dash plus exactly two digits.

After that cleanup, it is treated as a match when the browser title starts with the same text as the filename.

## Matches (Will Work)

```text
[1]
Filename      : My Video Title.mp4
Browser title : My Video Title - SiteName
Compared text : myvideotitle

[2]
Filename      : My-Video_Title!!.mp4
Browser title : My Video Title
Compared text : myvideotitle

[3]
Filename      : Scene Name-01.mp4
Browser title : Scene Name
Compared text : scenename

[4]
Filename      : the.best.clip.mp4
Browser title : The Best Clip (Official Upload)
Compared text : thebestclip

[5]
Filename      : ExampleTitle
Browser title : ExampleTitle Full Version 4K
Compared text : exampletitle
```

## Non-Matches (Will Not Work)

```text
[1]
Filename      : My Video Title.mp4
Browser title : Best Of My Video Title
Cleaned file  : myvideotitle
Cleaned title : bestofmyvideotitle

[2]
Filename      : Scene Name-1.mp4
Browser title : Scene Name
Cleaned file  : scenename1
Cleaned title : scenename

[3]
Filename      : Big Show The.mp4
Browser title : The Big Show
Cleaned file  : bigshowthe
Cleaned title : thebigshow

[4]
Filename      : Cool Clip Extended.mp4
Browser title : Cool Clip
Cleaned file  : coolclipextended
Cleaned title : coolclip

[5]
Filename      : A_B_C.mp4
Browser title : ABD
Cleaned file  : abc
Cleaned title : abd
```

## Practical Tips

1. Keep filenames close to the beginning of the original page title.
2. Use `-01`, `-02`, etc. if you split files into parts.
3. Avoid single-digit endings like `-1` if you expect part-number cleanup.
4. If matching is weak, rename the file so its beginning mirrors the page title more closely.

[Back to README](../readme.md)
