# urlstashgui
Use your browser history to find URL matches for scenes in StashApps
## Requirements (built and tested on...)
- StashApps
- Browser history
  - e.g. Mozilla %APPDATA%\Mozilla\Firefox\Profiles \<your profile>\**places.sqlite**
  - or Chrome %LOCALAPPDATA%\Google\Chrome\User Data\Default \**History**
- scenes with filenames that match the URL title in history
 - .mp4, -01, -02/etc, and any non-alphanumeric character will be ignored, including spaces.
## 

![Alternative text](how_to_basics1.jpg)

## Using the app
1. edit StashApp connection info if needed
  - your APIKEY is listed in http://localhost:9999/settings?tab=security if you have this feature enabled
2/3. With the popup, Browse to your browser history (mozilla is sqlite.places change file extension to see it, chronme is History no extension, again change file extension to see it)
  - This file is then copied to the folder with urlstashgui app. Your actual browser history is not modified.
  - Your browser history db is read and checked for a table matching mozilla structure or chrome structure, then copies url and title columns to file temp_browserHistory.db.
4. click "save history". this saves temp_browserHistory.db as browserHistory.db and deletes all duplicates.
  - browserHistory.db is appended if it exists already. so if you use this again you can import from different browsers or later after clearing browser history and retain all of your history that you want.
5/6. For those of us that dont want some of our history in this file, click clean URLs.
  - add any part of a url that you dont want matching with a scene, or just dont want to keep in the db.
  - If you've watched the scene, then you probably dont want your StashApp URL to be matching with your scene instead of the correct site...
  - This saves it again.
7. if you have used this app before, you can just type in a scene # to start near and click Load Scenes. it will use your browserHistory.db file automatically, and if you need to add your recent browser history, hop through steps 2 thru 6 again.
  - unless if you have a lot of scenes, starting scanning without entering anything into the textbox Scene ID # field is a good way to start.
  - Uncheck Skip orgnaized fields if you want (recommend to subsequently uncheck performers/etc. when scraping with the URLs of organized scenes later)
  - If you scenes are old and your browser is new, then just close the app and enter a more realistic scene number closer to your listed max scene # so you dont sit there all day.

8. it searches until it finds 10 scenes then shows the results. uncheck scenes you dont want updated. 
  - any existing URLs for your scenes are never modified. identically matching URLs are skipped automatically and will not appear as a result.
  - simple filenames are likely to give the same URL as another simple filename. if you cant scrape to get a SceneID, then it's not that bad to accidently match a few of those scenes with a bad URL. its easier to uncheck it now than to fix it later though
9. click Accept / Update URLs when you are ready to have the scene's URLs updated to stashapps.

*backward does nothing, sync scene file summary is for offline syncing but is missing another app component to function, help is out-dated, and I thinkrefresh/forward/loadscenes/accept are all almost the same thing
##
**Note: when you are done don't forget to scan your updated scenes with their URLs.**
 - When you are done with my app, open StashApps
 - Go to Tags, in the searchbox enter: urlhistory
 - Click urlhistory, then choose the tagger button on the right side of the search/filter menu
 - Source: Scrape with URL
 - Use a brain cell of attention to skip performers with made up names

 thanks
