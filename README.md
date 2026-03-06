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
-** Scenes with filenames that match the URL title in history ** 
  - `.mp4`, `-01`, `-02`, etc., and any non-alphanumeric character (including spaces) are ignored.
- a backup of your stashapps database and backup of your browser history, in case of 😭
  -  _Extensive_ testing has been performed on windows with chrome & mozilla and localhost w/out an apikey 👌

## 9 second clip of GUI with auto-accept on

![/img/urlstashgui_hq.gif](/img/urlstashgui_hq.gif)

## Using the app

1.  **Edit Stash connection info if needed** in Settings tab
     - Your APIKEY is listed in [http://localhost:9999/settings?tab=security](http://localhost:9999/settings?tab=security) if you have this feature enabled
       
2.  **Add browser history source** in DB Config tab
     - Mozilla uses `places.sqlite` Chrome uses `History`
     - Your actual browser history is not modified
       
4.  **Press Process Browser History** then go to Scenes tab and **Start**
   
6. **Any scene checked and then Accepted will have the matched URL and the Tag `urlhistory` saved to the scene**

7. **Use Stash Tagging mode and select `Scrape with URL` or go to the scene and press <img src="img/down_icon.svg" alt="Download" width="16">

   ### Additional Options

  - Skip organized
  - Auto-check threshold. If the number of URLs that match a scene reaches the threshold, that scene will be unchecked.
  - Auto-accept is recommended with a threshold of 3
  - Auto-startup loads any new browser history and begins searching from where you left off.
  - Connect multiple browser history files
  - Blacklist URL strings to remove unwanted missmatches (e.g. localhost -> removed from match database). Does not take regex.
  - Fix URL strings with find and replace logic (e.g. es.website.com -> website.com). Does not take regex.

8. **If you have used this app before, you can just type in a scene # to start near and click "Load Scenes".**  
   - It will use your `browserHistory.db` file automatically, and if you need to add your recent browser history, hop through steps 2–6 again.  
   - Unless you have a lot of scenes, starting without entering anything in the "Scene ID #" field is a good way to begin.  
   - Uncheck "Skip Organized Scenes" if you want (it’s recommended to also uncheck performers, etc., when scraping with the URLs of organized scenes later).  
   - If your scenes are old and your browser is new, close the app and enter a more realistic scene number closer to your max scene # so you don’t sit there all day.

9. **It searches until it finds 10 scenes, then shows the results.**  
   - Uncheck any scenes you don’t want updated.  
   - Any existing URLs for your scenes are never modified. Identically matching URLs are automatically skipped and won’t appear as a result.  
   - Simple filenames can produce the same URL as another simple filename. If you can’t scrape to get a SceneID, it’s not too bad to accidentally match a few scenes incorrectly—but it’s easier to uncheck them now than to fix them later.

10. **Click "Accept / Update URLs"** when you’re ready to update the scene’s URLs in StashApps.

*Backward does nothing, "Sync Scene File Summary" is for offline syncing but is missing another app component, "Help" is outdated, and I think "Refresh/Forward/Load Scenes/Accept" are all almost the same thing.*

---

I did not write a single full line of any of this code. ChatGPT did it all.

---

## 
**Note: When you are done, don’t forget to scan your updated scenes with their URLs.**
- Open **StashApps**  
- Go to **Tags**, and in the search box enter: `urlhistory`  
- Click **urlhistory**, then choose the tagger button on the right side of the search/filter menu  
- Source: **Scrape with URL**  
- Use a brain cell of attention to skip performers with made-up names

Thanks
