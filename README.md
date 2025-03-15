# mozhisStashGUI
Use your mozilla browser history to find URL matches for scenes in StashApps
## Requirements (built and tested on...)
- StashApps (v0.27.2-83 thru 88)
- Python 3 (3.13)
- Mozilla (135.0.1, non-windows store version)
- scenes with filenames that match the URL title in history
 - e.g. filename can be used to search your browser history for the originating URL

## Using non-Mozilla browser history
1. For Chrome you can look for a working browser history exporter. Other browsers you may be able to use sqlite3 db software to locate the URL + Title.
2. Import browser history into Mozilla (more extensions) or make your own sqlite3 database and rename it to places.sqlite.
   - the only data you need is a table named moz_places containing columns url and title.
   - removing rows is not necessary, the app will make a copy and cleanse sites automatically
   - app was tested with >50k rows (~50MB total)
3. Confirm you know where your browser history is. If you install Mozilla on M$ store then it has a different path than the app will try to use.

(/how_to_basics1.jpeg)
## Using the app
1. open python file (yaml file editing is optional)
2. edit StashApp connection info if needed
  - APIKEY is listed in http://localhost:9999/settings?tab=security if you have this feature enabled
3. click "Copy places.sqlite" and browse to your Mozilla profile. Select places.sqlite.
  - This file is then copied to the desktop. Your actual browser history is not modified.
4. click "Load Scenes". This connects to your StashApps and will populate your max Scene ID # and begin searching.
5. it searches until it finds 10 scenes then shows the results. uncheck scenes you dont want updated. 
  - any existing URLs for your scenes are never modified. identical URLs are skipped automatically and will not appear as a result.
6. click Accept / Update URLs when you are ready to have the scene's URLs updated to stashapps.
7. skip all scene matches by clicking Forward >> or uncheck all/manually unchecking all scenes.
8. search by scene id (skip around...) by entering a scene id in the Start Scene ID box. it doesn't matter if you have a scene id with that #
