# urlstashgui
Use your browser history to find URL matches for scenes in StashApps

## Stuff you need 
- StashApps
- Scenes with filenames that match the URL title in history.
  - This app is only helpful if you have files that are named based on the websites title.
  - Commonly seen with many yt-dlp or downloader apps.
- Browser history  
  - e.g. Mozilla `%APPDATA%\Mozilla\Firefox\Profiles\<your profile>\places.sqlite`  
  - or Chrome `%LOCALAPPDATA%\Google\Chrome\User Data\Default\History`
- **Scenes with filenames that match the URL title in history** 
  - `.mp4`, `-01`, `-02`, etc., and any non-alphanumeric character (including spaces) are ignored.
- (optional) a backup of your stashapps database and backup of your browser history
  -  _Extensive_ testing has been performed on windows with chrome & mozilla and localhost. 

## Clip of GUI with auto-accept on

> clip plays at actual speed. blurring effect added for privacy

![/img/urlstashgui_hq.gif](/img/urlstashgui_hq.gif)

## Using the app

1.  **Edit Stash connection info if needed** in Settings tab
     - Your APIKEY is listed in [http://localhost:9999/settings?tab=security](http://localhost:9999/settings?tab=security) if you have this feature enabled
       
2.  **Add browser history source** in DB Config tab
     - Mozilla uses `places.sqlite` Chrome uses `History`
     - Your actual browser history is not modified
       
4.  **Press Process Browser History** then go to Scenes tab and **Start**
   
6. **Any scene checked and then Accepted will have the matched URL and the Tag `urlhistory` saved to the scene**

7. **Use Stash Tagging mode and select `Scrape with URL` or go to the scene and press <img src="img/down_icon.svg" alt="Download" width="16">**
     - You can also filter by **Tag** `urlhistory`
     - This repo has `Scrape with URL` saved in `/00ScrapeURL/`. Copy this folder and its contents into your scraper folder if you want it at the top of your scraper list.
     - Using the `Identify` option in Stash works too, but some sites do not have accurate `Performer` tags when scraping by URL.

   ### Additional Options

  - Cursor over the matched URL to see all matches in tooltip
  - Skip organized
  - Auto-check threshold. If the number of URLs that match a scene reaches the threshold, that scene will be unchecked.
  - Auto-accept is recommended with a threshold of 3
  - Auto-startup loads any new browser history and begins searching from where you left off.
  - Connect multiple browser history files
  - Blacklist URL strings to remove unwanted missmatches (e.g. localhost -> removed from match database). Does not take regex.
  - Fix URL strings with find and replace logic (e.g. es.website.com -> website.com). Does not take regex.

---

Thanks
