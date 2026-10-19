# Video Producer: user guide

Français : [Video Producer : guide utilisateur](/docs?doc=plugin/video-producer/user-guide.fr) (fichier `docs/user-guide.fr.md`).

This guide explains how to make a short film with Video Producer. Interface labels are written in **bold**. The interface is complete, in English and in French. Your projects are saved as you work, your media are imported from PotionUI, and takes and finals are real videos (chapters 8 and 9). The PotionUI assistant has its own mode (chapter 10), shots are joined at their seams (chapter 12), and delivery is real: videos for the web and for social networks, files for other software and subtitles (chapter 14). A few functions are simulated and marked as such (chapter 17). The administrator guide is a separate page that only admins see.

## 1. What Video Producer is

Video Producer is a PotionUI plugin for audiovisual editing, AI sequence generation, art direction, sound creation and 3D scene preparation, all in one page. You write a synopsis, split it into shots, generate quick draft takes, choose the best one, turn it into a final, then cut, match colors, mix sound and deliver. It opens from the **Video Producer** entry in the sidebar.

Before you start:

- An admin has to prepare at least one engine (this machine, a studio server or a cloud model) and at least one video preset assigned to you. If the Production bar shows no engine, see chapter 18.
- Your admin also sets the draft resolution, how many generations you can have in progress at once, and may limit the GPU minutes you can use per month.
- Generation is real: the takes are videos made by your admin's machines or cloud account, and they take time. The estimate in the Production bar tells you what to expect before you start (chapter 8). As a measure, on a 12 GB graphics card a 5-second draft took about 6 to 7.5 minutes with the presets named (12 GB) and about 26 minutes with Wan, and a final by upscale to 1080p took more than two hours.
- The machine your admin runs decides what you can use. A preset whose name ends with a card size is set up for a graphics card of that size, and the engine pop-up adds the ordinary memory (RAM) the server needs (chapter 8). On an 8 GB card, pick **Wan 2.1 T2V 1.3B (8 GB) · 32 GB RAM** or **Wan 2.2 TI2V 5B (8 GB) · 32 GB RAM**: they make 480p clips of up to 5 seconds from the text alone. On a 12 GB card, pick **MiniMax H3 (12 GB) · 64 GB RAM** or **MiniMax H3 Fast (12 GB) · 64 GB RAM**: the other MiniMax H3 presets are made for bigger cards (the Fast one ran out of memory on a 12 GB card in our tests). Ask your admin which card they have.
- Delivering a video file needs ffmpeg on your PotionUI server. If the export window says that ffmpeg is missing, ask your admin (chapters 14 and 18). The files for other software and the subtitles do not need it.
- The assistant needs a language model that your admin has configured in PotionUI and assigned to you (chapter 10). Ask your admin to connect a local model server set up for the assistant (llama.cpp `llama-server` or Ollama) or an online provider: the model built into PotionUI ran out of memory or could not call the tools on a 12 GB graphics card in our tests. Everything else works without it.
- The model MiniMax H3 (the **MiniMax H3** entries of the engine pop-up) comes with a license that excludes use, and anything generated with it, in the European Union, the United Kingdom, the United States and South Korea without an individual authorization from MiniMax, and that asks a commercial product to display "MiniMax H3" prominently. Ask your admin before you use it. Video Producer does not check any of this for you.

The interface is in English by default and also exists in French (chapter 15).

The first time you open the page, it creates a starter project, "Dawn at the harbour" ("Aube sur le port" in French), and opens it. It holds a synopsis, the global direction in five fields, five shots of 5 seconds still to generate, each with its shot prompt (the sleeping harbour, the fisherman's hands, the departure, the gulls, out to sea), a title, a marker named "Cast off" and four empty audio tracks. It has no media, no take, no reference and no 3D scene. Its name, synopsis, shot names, title and marker are written in the language of the interface; its global direction and shot prompts are written in the prompt language of the project, English by default (chapter 15). Try the whole path on it, or start an empty project with **File › New project…**. On your next visits the page opens the project you used last (chapter 5).

## 2. The path in eight steps

**Help › Getting started** shows the same path as a list you can click. The eight steps:

1. **Create a project.** **File › New project…** (or **File › Open…** for an existing one). In **Project properties…** you set the name, the aspect ratio (16:9, 2.39:1, 9:16, 1:1 or 4:5), the resolution (720p, 1080p or 4K) and the frame rate (24, 25 or 30 fps). Result: an empty project that is saved as you work.
2. **Set the global direction.** In the **Director IA** workspace, tab **Direction**: world and intent, characters and identity, photography, palette and lighting, pacing and continuity. Result: a text that guides every generation.
3. **Add the references.** In **Director IA**, tab **References**: identities, 3D sets and motion guides. Result: what must stay the same from one shot to the next.
4. **Split the film into shots.** In the **Storyboard** workspace: write the synopsis, then click **Propose a breakdown** (one sentence becomes one shot) or ask the assistant to cut it (chapter 10), keep the shots you want and adjust their shot prompts. Result: a row of shot cards.
5. **Generate drafts.** In the Production bar, pick the **Generation engine**, quality **Draft**, then **Generate selection** (Ctrl+G). The estimate shows time, memory and quota. Result: real draft takes A, B, and so on, made by the engine you picked.
6. **Pick and make final.** In the Inspector, tab **Takes**: compare the takes, click **Choose** on the one the shot should play, then click **Make final** on the best draft take. Result: the shot moves from Draft to Final.
7. **Edit, match and mix.** Fades on the clips, color match in the Inspector tab **Color**, seam frames between shots (chapter 12), the console in **Mix**. Result: a finished sequence.
8. **Prepare delivery.** **File › Export video…**, **Export to other software…** or **Export subtitles…**. Result: a video in your library and files you can download.

All eight steps work for real, and your projects are saved as you work (chapter 5). The page opens the project you used last, or the starter project the first time (chapter 1). **New project…** starts an empty project, "Untitled project", and adds it to your projects. Drafts and finals are real videos made by your admin's engines. Delivery is real for the web and social videos and for the files for other software (chapter 14); the master file, the archive and the audio stems of the export window are simulated (chapter 17).

## 3. The screen

The page has five levels of controls, from the widest to the most local, around a left panel, a center area, the Inspector and the timeline:

- **Menu bar.** Ten menus, in this order: **Video Producer**, **File**, **Edit**, **Cut**, **Shot**, **Production**, **Audio**, **View**, **Window**, **Help**. The **Video Producer** menu holds **About Video Producer**, **Preferences…**, **Keyboard shortcuts** and **Search commands…**. A menu shows "…" only when the command opens a window that asks for something, and a check mark in front of a state that is on.
- **Project bar.** On the left, the button that shows or hides the side panel, the project name (click it to rename the project) and its save state ("Saving…", "Saved at" and the time, "Modified · click to save" or "Not saved — retry"; chapter 5). In the middle, the workspace selector: **Media**, **Director IA**, **Storyboard**, **3D scene**, **Mix**. On the right, **Import**, **Export**, **Assistant** (it opens the PotionUI chat, chapter 10), a search button for the commands and the button that shows or hides the Inspector.
- **Production bar.** It targets what to generate and holds the only main button of the page, **Generate selection** (chapter 8).
- **Area headers and the timeline toolbar.** A title and counters on the left, small icons on the right.
- **Content.** Small buttons that appear when you hover or select.

A rule to remember: every other entry point (Storyboard, side panel, Director IA) only targets what to generate; the Production bar is the one that acts.

The ten menus group all the commands of the page. The command search (**Search commands…**, Ctrl+K) finds any of them by name, shows its menu and its shortcut, and runs it with Enter.

| Menu | What it holds |
|---|---|
| **Video Producer** | About, Preferences, Keyboard shortcuts, command search. |
| **File** | New project, Open, Save, Version history, Import files, From the PotionUI gallery, Project properties, the three exports. |
| **Edit** | Undo, Redo, Copy, Paste, Duplicate, Delete, Search media. |
| **Cut** | The three tools, Split at playhead, trims, Change duration, in and out points, Clear range, Add marker, Add title, Fade in and out. |
| **Shot** | New shot, Info, Show source, Shot takes, Make take final, Shot color, Match color to previous shot, Camera keyframes, Favorite, Reject, Remove flag. |
| **Production** | Global direction, Split synopsis into shots, Continuity check, Generate selection, Draft and Final quality, the queue, Cancel the generation, Results and takes, Assemble chosen takes, Advanced workshop, the engine, the Hybrid builder. |
| **Audio** | Add audio track, Import audio file, Mixing console, Voice and dialogue and the sound design workshop. |
| **View** | Play, loop, full screen, framing guides, Compare takes, Luminance scope, Audio meters, timeline zoom, Snapping. |
| **Window** | The five workspaces, the reference spaces, Side panel, Inspector, PotionUI assistant, Prompt library, Timeline index, Background tasks. |
| **Help** | Getting started, Keyboard shortcuts, Search features, Simulated features. |

### The areas of the page

- **Left panel.** It changes with the workspace (chapter 4). Show or hide it with the first button of the project bar or with Ctrl+Alt+1.
- **Center.** The viewer, the storyboard cards, the board of references or the 3D view, depending on the workspace.
- **Inspector.** On the right. It follows the selection (chapter 7). It starts hidden when the window is narrower than 1360 pixels: open it with the last button of the project bar, or select something, which opens it.
- **Timeline.** At the bottom. In **Mix**, the mixing console takes its place and a button brings the timeline back. Drag the thin line above the Production bar to give it more or less height.
- **Status bar.** At the very bottom, from left to right: the language reminder (`EN` or `FR`; click it to open the Preferences), the number of shots with the duration, the resolution and the aspect ratio, the active tool, the selection, the range. On the right: the number of direction points to check (click it to open the **Direction** tab), the generation queue, snapping and, when your admin has set a limit for you, your **GPU quota**, the minutes used this month out of that limit (cloud providers are billed separately).

The viewer has its own transport bar: monitor volume, go to the start, previous and next frame, play, loop, the timecode, framing guides, aspect ratio, resolution and full screen. When you preview a take, a comparison or a source media, a pill at the top of the viewer brings you **Back to the sequence**.

The timeline has a toolbar and one row per kind of item. The toolbar holds **Undo** and **Redo**, the **Select tool**, **Range tool** and **Blade tool**, **Split at the playhead**, **Duplicate**, **Delete**, the **Add** menu (**Prompt**, **Reference frame**, **Control video**, **Title**, **Marker**, **Audio track**), **Snapping**, the zoom and **Fit**. The rows are **Titles**, **Prompts**, **Frames**, **Control video**, **3D shot**, **V1 · Video** and one row per audio track, with **M** (mute) and **S** (solo). Click the ruler to move the playhead; with the Range tool, or by dragging with Alt held, draw a range. Drag a shot to change its order, drag its edges to trim it (the shots after it follow), drag the white handles at the top of a clip to set its fades, drag an audio clip to another track. The trim and fade handles are for the mouse; from the keyboard, use **Cut › Trim start to playhead**, **Trim end to playhead** and **Fade in and out**, or the **Duration and source** and **Fades** fields of the Inspector (chapter 7). Ctrl and the mouse wheel zoom. Double-click an empty spot of the Prompts, Frames or Control video row to create an item there.

## 4. Workspaces

Each workspace changes the left panel and the center. The Inspector on the right follows your selection in all of them. **Window › Timeline index** lists the prompts, frames, markers and Control videos with their time, and **Window › Background tasks** shows the generation in progress and the queue.

### Media

The media of the project in one panel. A new project has none: the panel says "No media in this project." and offers **Import media**, like the import button of its header and **Import** in the project bar; chapter 6 explains how to bring in your images, videos and audio files. Filter with the collection pills (**All**, **Images**, **Videos**, **Audio**, **Generated**), search by name without worrying about accents, double-click to preview, drag to the timeline. For a selected item the panel shows its duration, format, collection and origin, and the buttons **Preview**, **Add to cut** and, for images and videos, **Use as frame at the playhead**. The center is the viewer.

### Director IA

The left panel has three tabs. A dot on **Direction** warns that there are points to check, and **Results** shows the number of takes.

- **Direction.** Shows what guides the generation for the current range: the global direction, the shot prompt, the references and Control videos, with **View the generation summary**. Below, **To check**, the list of direction conflicts and color matches to fix (each color match comes with **Match** and **Use the previous shot’s last frame**, chapter 12), the section of the assistant's continuity check (also titled **To check**) with its button **Ask the assistant to check continuity** (chapter 10), the **Project H3 profile** (FL2VA, Ref2VA or Hybrid AV, chapters 8 and 11) and the **Global direction** itself, in five fields (world and intent, characters and identity, photography, palette and lighting, pacing and continuity), with a counter out of 4000 characters. Each field has a **Library & assistant** link. The gear button, **H3 settings**, opens the **Advanced workshop**.
- **References.** Three families, **Images and identity**, **3D sets** and **Motion guides**. A reference is global (it goes with every generation) or applies to a range only; **Attach to range** sets the second. **Reference** adds one. The center shows the board of references, in two groups, **Global direction** and **On the timeline**, with a search field. Drag a thumbnail onto the Frames track to anchor it to a precise moment. A new project has no reference: the board says so, and **Reference** adds the first one.
- **Results.** The take cards of each shot (chapter 9), the **Generation queue** and **Assemble chosen takes**.

### Storyboard

On the left: the **Synopsis** (one sentence becomes one shot) and **Propose a breakdown**. The **Proposed breakdown** lists the shots: tick the ones to keep, rename them and click **Add N shots at the end**. The breakdown of that button is simple: it only cuts the synopsis into sentences (its tooltip says "Sentence split; ask the assistant for a real breakdown"). The assistant makes a real breakdown and fills the same list (chapter 10). Then **To produce**, with **Drafts left** and **Move to final** (the number of shots and the footage still to do for each), and **Continuity**, which lists the color matches to check, each with **Match color** and **Use the previous shot’s last frame** (chapter 12).

In the center: one card per shot, in order, with its number, its duration, its name, its stage (**Source**, **To generate**, **Draft** or **Final**), its number of takes and its shot prompt; click the prompt to write it. Drag a card to move it. The buttons of a card appear when you hover it or select it: the main one follows the stage, **Generate**, **Make final**, **See takes** or **Regenerate**, and three icons show the shot in the viewer, insert a shot after it and delete it. While a take of the shot is in progress, the card shows its step and progress and the button is disabled. The header counts the shots per stage, adds one with **Shot** and sets the size of the thumbnails; a **New shot** tile at the end does the same. In this workspace, the Left and Right arrow keys move the selection to the previous or next shot.

### 3D scene

The 3D scene turns a picture into a set you can film from other angles. A new project has none: the center says "No 3D scene" and offers **New scene from image…** and **Import splat or Blender file…**, which the **Scenes** list of the left panel and the **Window** menu offer too.

- **New scene from image…** builds a Gaussian Splat, a cloud of small colored blobs that a camera can move through, from one picture. Pick the source: **Shot frame** (the frame of the shot under the playhead, taken from its video, for example a take you generated), **Project image** or **Library** (a picture of your PotionUI library, which joins the media of the project). Name the scene and click **Build the scene**. The scene is built on the generation queue, like a take, in a few seconds to a minute, and counts against your GPU minutes. The list shows its progress with a cancel button, the project bar shows a dot on **3D scene** and the status bar the percentage; "Scene ready" tells when it is done. A scene that failed offers **Try again**.
- **Import splat or Blender file…** adds a `.ply`, `.spz` or `.splat` splat, or a `.glb` or `.gltf` file exported from Blender (meshes, cameras and their animation), up to 1 GB. A `.gltf` must hold its textures and data (64 MB at most); one that points to separate `.bin` or image files is refused: export a `.glb` instead (glTF Binary in Blender).

The center draws the selected scene in the frame of your project. Drag to orbit around the target, drag with the right button (or with Shift) to pan, scroll to move in or out, and scroll with Alt to change the focal length. **Source view** goes back to the camera of the picture. With the keyboard, once the view has the focus (Tab, or a click in it), the arrow keys orbit, Shift and the arrows pan, + and − move in and out, and 0 goes back to the source view. If your graphics card drops the 3D view, the view says so: click **Try again**. If it offers **Reload the page**, the plugin was updated while the page was open. The top left shows the focal length with the vertical and horizontal angles of view; the top view at the bottom right shows the source camera (circle), the target (square), the current camera and the path of the 3D shot. A picture only holds about ±10° of camera movement: for a scene built from a picture, the gauge at the bottom left shows how far the camera is from the source view, and turns red with "Holes likely" beyond 15° or 25 %, where empty patches appear behind the objects. Nothing is blocked.

#### Capture an angle for another shot

Place the camera, then click **Capture for a shot…**. The window shows the capture at the resolution of your project and how much of it is empty. Pick the shot (by default the selected shot, or the one under the playhead) and the use:

- **First frame** or **Last frame**: the capture becomes the first or last frame of that shot, so the generation starts from this new angle or ends on it (FL2VA). If the shot already has one, you confirm the replacement. The frame shows a cube on the **Frames** row.
- **Reference**: the capture becomes a **3D sets** reference of the shot. It keeps the set consistent, while the framing still comes from the prompt (Ref2VA).

#### Move the camera along a path

A **3D shot** is a camera path on the timeline (row **3D shot**). **New 3D shot at the playhead** creates one for the current scene. Give it its path:

- **Preset trajectories**: **Orbit** (±10° around the subject), **Push in** (15 % of the distance) and **Rise** (+10°, tilting toward the subject), with the **amplitude** slider below; moving the slider updates the path of the selected 3D shot. Beyond 15° or 25 % the panel warns that holes are likely.
- **Keyframe**, in the Inspector, stores the camera at the playhead; **Follow the path** shows the camera of the path again after you moved it.
- **Blender camera**: for a Blender scene, pick an animated camera and click **Use this camera**. Its animation becomes the path, at 24 frames per second, and the 3D shot takes its length.

Play to preview the path. Then, under **Outputs for generation**:

- **Render reference video** renders the 3D shot frame by frame at 24 frames per second and turns it into a video of the project, placed as a **Control video** on the shot. The bar at the bottom of the view counts the frames, and **Cancel** stops it until the server starts encoding the video. Its size is the frame of your project with the long side at most 1280 pixels (1280 × 704 for 1080p in 16:9), as the panel says: the engines reduce it to their own size anyway. Keep the tab visible while it renders: a hidden tab renders much more slowly. A reference video needs at least 2 seconds. When you change the path, the scene or the length of the 3D shot, or move it onto another shot, the video is marked out of date: render it again. Deleting a 3D shot deletes its Control video. While a render or a capture runs, you cannot change or remove the scene.
- **Use start and end as first and last frames** captures the start and the end of the path and sets them as the first and last frames of the shot, so that the engine moves the camera between these two angles. This works today with FL2VA, on 12 GB too.

Three output modes use these videos (chapter 8).

### Mix

The **Sound design workshop**, the **Project sounds** (drag one to a track, or use its plus button to add it at the playhead), the **Roles** (**Dialogue**, **Music**, **Ambience**, **SFX**) with their number of tracks, and the mixing console, which takes the place of the timeline: faders, **M** and **S**, pan, equalizer, compressor, filter, reverb and delay sends, meters and an automation mode. The center is the viewer. The four tracks of a new project are empty, and **Project sounds** says "No sounds in this project." until you import one (chapter 6). The console plays the audio files you import (chapter 13); the sounds that the workshop prepares are synthesized by your browser. The workshop and the automation curves are simulated: see chapter 17.

## 5. Projects

Your projects are saved on the PotionUI server, in your account, as you work. There is no file to keep and nothing to export to avoid losing them. The page lists only your own projects.

### Opening the page

The page opens the project you used last. If it no longer exists, it opens your most recently modified project. If you have none (your first visit, or you deleted them all), it creates the starter project (chapter 1) and opens it.

### Saving

The page saves by itself, less than a second after your last change. The project bar shows the state under the project name:

| State | Meaning |
|---|---|
| "Saved at" and the time | What you see is what is saved. |
| "Modified · click to save" | You made a change that is not saved yet. It is saved a moment later; click the state to save at once. |
| "Saving…" | The save is under way. |
| "Not saved — retry" | The save failed. A message tells why, with a **Retry** button; click the state to try again. The next change tries again too, and your changes stay in the page. |

**File › Save** (Ctrl+S) saves at once and shows "Project saved". The page also tries to save when you switch to another browser tab and when you leave it. To rename the project, click its name in the project bar: the name is saved with the project and shows in the list.

A failed save shows one of three messages: "Could not save the project." (a network or server error), "The project could not be saved: its content was refused." or "The project is too large to be saved." (the data of a project, without the media files, is limited to 4 MiB). A retry does not fix the last two: ask your admin.

### Open

**File › Open…** (Ctrl+O) opens the window **Open a project**. It lists your projects, the most recently modified first. Each row shows the project name, then when it was modified, its number of shots and its duration. The project that is open carries the badge **Current**. A capture of this window, in the dark and light themes of the English interface, is in `docs/screenshots/open-window.png`.

- Select a row, then click **Open**. Double-clicking a row or pressing Enter on it does the same. **Open** is disabled while the selected row is the project that is already open. The page saves the current project before it opens another one. If that save failed and changes are waiting, a window titled "Unsaved changes" says that the changes could not be saved and will be lost: **Discard changes** goes on, and cancelling keeps the project that is open.
- **New project** (bottom left) creates an empty project, like **File › New project…**.
- The trash icon at the end of a row deletes that project, after a confirmation that tells you that the project and its versions will be deleted and that this cannot be undone. The project that is open has no trash icon. Deleting a project cancels the takes it still has in progress. It does not delete the media in your library or gallery, nor the videos of its takes, which stay in your generation history.
- The window says "Loading projects…" while it loads, "No saved project" when you have none, and "Could not load your projects." with a **Retry** button when the server did not answer.

**File › New project…** saves the current project, then creates an empty project, "Untitled project", opens it and shows "New empty project created". It asks for a confirmation (**Create an empty project**) only when the current project could not be saved.

### Version history

**File › Version history…** opens the window **Version history** ("Each save creates a version"). It lists the versions of the open project, the newest first. Each row shows the number ("Version 7"), the date and time, seconds included, and the number of shots. A capture of this window, in the dark and light themes of the English interface, is in `docs/screenshots/version-history.png`. A version made by a restore adds "Restored from version N". A version written by the assistant adds "Assistant" (chapter 10). The version you are working on carries the badge **Current** and cannot be selected.

To go back, select an older version and click **Restore**. A window asks you to confirm ("Restore version N": the project goes back to that version and the current state stays in the history). If the last save failed and changes are waiting, a second window, "Unsaved changes", asks you to confirm that they are lost (**Discard changes**). Then the project becomes that version and the page shows "Version N restored". The restore is itself a new version at the top of the list, so nothing is lost and you can restore the state you came from. **Cancel** closes the window.

Your admin limits how many versions are kept per project (50 by default) and the oldest are deleted first. Every save that changes the project creates a version and the page saves often, so the limit can be reached quickly: ask your admin for a higher one if you need a longer history.

### When the project changed elsewhere

If you open the same project in two tabs, windows or devices, the page that saves second started from an out-of-date version, and the server refuses its save. That page then loads the saved version of the project and shows "Project reloaded: it changed elsewhere". The changes you had not saved in this page are lost, and nothing is merged. Work on a project in one place at a time. **File › Version history…** brings back an earlier state if you need it.

### When the project was deleted elsewhere

If you delete the project from another tab or device while it is open here, the next save is refused because the project no longer exists. The page stops saving it, shows "This project was deleted elsewhere", then opens your most recently modified project, or creates the starter project if you have none. If that fails, the page shows "Could not open Video Producer" with a **Retry** button. The changes you had not saved are lost.

### Undo and redo

**Edit › Undo** and **Redo** (Ctrl+Z, Ctrl+Shift+Z) work on the changes you made in the page, up to 100 steps. The history is kept in the page, not in the project: loading the page again, opening another project, creating a project, restoring a version and a reload after a conflict all empty it. An undo is a change like any other, and it is saved too.

## 6. Media

The media of a project are the images, videos and audio files you imported, and the takes of the project (chapter 9). The **Media** workspace lists them (chapter 4).

### Importing

- **Images and videos.** **File › Import files…** (Ctrl+I), **Import** in the project bar, the import button in the header of the Media panel and **Import media** in an empty panel open the window **Import images and videos**. It is the PotionUI picker of your library: the files you uploaded to PotionUI and the generations you copied there.
- **From the gallery.** **File › From the PotionUI gallery** opens **Import from the gallery**, with your past generations. Every file of a generation can be picked on its own. Only images and videos can be picked.
- **Audio.** **Audio › Import audio file…**, the **Sound** button of **Project sounds** in the **Mix** workspace and the **Import** button of the console open **Import audio files**, the picker of your library with audio only.

In each picker you tick several files and confirm them together. The files then appear in the Media panel and the page shows, for example, "2 files imported". A media that is already in the project (same origin) is not imported again: the page counts it apart, for example "2 files imported · 1 file already in the project", or "1 file already in the project" when nothing is new. When some cannot be imported it adds, for example, "1 file could not be imported": the file is no longer available, or its kind is not accepted by the window. If your server has no picker, the page says "The media picker is not available on this server."

An import copies nothing: the project keeps a reference to the library item or the gallery file, and the address the page uses to show it. If you delete the file from PotionUI, the project can no longer show or play it.

### In the Media panel

After the import, your browser reads the duration and the size of each file. The duration shows at the bottom right of the thumbnail. For the selected item the panel shows **Duration**, **Format**, **Collection** and **Origin**: **Gallery** or **Library**; the thumbnail carries the same word. The frame rate of an imported video comes from the library when the library knows it, and shows after the size (for example "1280×720 · 25 fps"); otherwise, and for a gallery file, **Format** shows the size only. The collection pills sort images under **Images**, videos under **Videos** and audio files under **Audio**. **Generated** holds the videos of the finished takes of the project (chapter 9). A capture of the panel after an import is in `docs/screenshots/media-import.png`.

### Thumbnails

An image is its own thumbnail. For a video, the page uses the thumbnail that PotionUI made for it when there is one, and otherwise a frame that your browser captures from the file. Thumbnails are not saved in the project: they are made again when the project opens. They show wherever a media or a shot shows its picture: the Media panel, the Inspector, the timeline and the viewer.

### Playback

- **Video and images.** Put the media in the cut (**Add to cut**, or drag it to the timeline). The viewer then plays the real video in step with the playhead, or shows the image, with the fades and the color settings of the shot. To look at a media on its own, double-click it or click **Preview**: the viewer shows it, a video with the controls of your browser and an audio file with an audio player, and **Back to the sequence** brings you back.
- **Sound of a video.** The viewer does not play the sound of a video. Sound comes from the audio tracks (chapter 13).
- **Audio.** An audio file placed on a track plays through its strip of the console. The faders, mute and solo, pan, equalizer, compressor, filter and sends act on the real sound, the meters show it, and the clip draws the waveform of the file in the timeline (chapter 13).

What is simulated here: the sounds of the Sound design workshop, which your browser synthesizes (chapter 17). The takes of the real generation are ordinary videos and play like any other video (chapter 9). When the file of a shot's media is no longer reachable (you deleted it from your library or gallery), the viewer shows **Media offline** ("The source file of “…” is no longer available: import it again or choose a take.") and so does the thumbnail of the shot on the timeline.

## 7. Inspector

The Inspector follows the selection and its title tells what is selected: **Video shot**, **Audio clip**, **Title**, **Shot prompt**, **Reference frame**, **Control video**, **3D shot**, **Marker**, **Reference** or **Console strip**. For a shot it starts with a thumbnail, the name (click it to rename the shot), the stage and the times, and has three tabs:

- **Shot.** A shortcut to the next action (**Generate drafts**, or **Make take A final**) with the engine it will use ("On" followed by the engine), **Duration and source** (the duration, where the shot starts in its source and the length of the source), **Frames** (the **First frame** and the **Last frame** of the shot, and the button **Use the previous shot’s last frame**; chapter 12), **Fades** (**In** and **Out**), the **Flag** (**None**, **Favorite** or **Rejected**) and three icons to split the shot in the middle, duplicate it and delete it.
- **Takes.** The take cards of the shot, as **Final** and **Drafts**, and a button that makes more drafts (for example "2 more drafts"; chapter 9).
- **Color.** The luminance scope, the match with the previous shot, presets and fine settings (chapter 12).

The other items have their own panel:

- **Audio clip:** its track, start, duration, gain, fades, and a button that opens its strip in the console.
- **Title:** the text, the subtitle, the start and the duration.
- **Shot prompt:** the text, the **Library & assistant** link, the **Editor** button, the warnings about the direction, the start, the duration, the influence, and the global direction that applies.
- **Reference frame:** the image (picked among the images of the project, which a new project does not have), the position, the role (start, end, transition, identity, style), the strength of its influence and, for a capture of a 3D scene, the scene it comes from.
- **Control video:** the name, its source (**3D scene** or **Imported video**), the start, the duration and the strength of its guidance. In its range the motion comes from the guide: camera instructions in the prompts are ignored. For the reference video of a 3D shot: the video, **Open the 3D shot “…”** and, when it is out of date, **Render again**.
- **3D shot:** the scene, the start, the duration, the camera path (a preset with its amplitude, manual keys or a Blender camera), the state of its reference video with **Render video** and **Start and end**, and the **Camera**.
- **Marker:** the label and the position.
- **Reference:** the name, the role, the scope (**Global direction** or **Specific moment**) and the shot it applies to.
- **Console strip:** the name, the role, the effects (**Equalizer**, **Compressor**, **Filter**) and the sends.

In the **3D scene** workspace, with a 3D shot selected or nothing selected, the Inspector shows the **Camera**: focal length, roll and distance, **Keyframe**, **Follow the path**, **Source view** and the keyframes of the 3D shot (for a Blender camera, the number of sampled keys). With nothing selected in the other workspaces, it shows the project (format, H3 profile, content), a reminder of the main shortcuts and a **Project properties…** button.

## 8. Production bar and generation

The Production bar reads like a sentence: a target (**Shot**, **Range** or **Sequence**), the range with the number of shots and prompts it holds, a quality (**Draft** or **Final**), an output mode, the **Generation engine**, the **Advanced workshop**, then the estimate, **Add to queue** and **Generate selection**. A number with a warning icon after the counters is the number of direction conflicts in the range; click it to see them. Generation is real: a take is a video made in the background by the engine you pick.

### Choose the engine

- The output mode **AI generation** generates the takes. With the Ref2VA profile, the up-to-date reference videos of a shot (chapter 4) go with its references, with the picture their scene was built from. The prompt tells the engine to take only the camera movement from these videos, spelled out in words ("the camera arcs from left to right around the subject…", played forward), and their look from the picture and your text, never their rendering defects. **3D render** generates nothing: the main button reads **Place the 3D renders** and makes each shot that has an up-to-date reference video play that video. **3D render + AI** generates Ref2VA takes guided by these videos, whatever the profile of the project; it needs a MiniMax-H3 preset with the reference mode.
- The **Generation engine** pop-up lists what your admin enabled and assigned to you, in groups named after the backends. A group named after your admin's own backend holds the video presets that run on their hardware, for example **Wan 2.1 / 2.2**, **MiniMax H3** or, on a 12 GB card, **MiniMax H3 (12 GB)**. Each cloud provider has its own group, with its video models by name. Your choice is saved with the project. Whether a preset runs on this machine or on a studio server is decided by PotionUI, and the take card tells you afterwards. Hover the pop-up to see the group and, for a preset that runs on the admin's hardware, the free memory of its GPU ("16.0 / 24.0 GB free"). On a window narrower than 1400 pixels the pop-up is hidden: use **Production › Generation engine…**, which opens the **Advanced workshop** on its engine step. A capture of the pop-up and of the bar around it, in the dark and light themes of the English interface, is in `docs/screenshots/engine-popup.png`.
- With no engine, the pop-up reads "No engine" and the bar says "No generation engine: an administrator must enable a video preset or a cloud model." An admin also sees the link "Open plugin settings". When the engine of a project is no longer available, the pop-up reads "Engine no longer available" and the bar says "The engine of this project is no longer available: pick another one." A project from an earlier version that named a placeholder engine is moved to the matching real engine when you open it.
- **Quality.** **Draft** makes quick takes at the resolution your admin chose, or the closest the engine offers; hover it to see which ("Quick draft in 832×480: check motion and framing"). **Final** makes takes at the largest resolution of the engine ("Final quality in 1280×720: keep it for the chosen takes"). To improve a draft you like, **Make final** (chapter 9) is usually the better way: it keeps the picture you chose.
- The **Advanced workshop** has three steps: **Sources and guides**, **Engine and Hybrid builder** and **Sound and delivery**. It opens from the bar, from **Production › Advanced workshop…** and, for the engine, from **H3 settings** in Director IA. Its **Variants per window** field (1 to 4) sets how many takes, A, B and so on, each shot gets when you generate. The settings that the engine does not use are greyed there and carry the badge "Not sent with this engine" (chapter 17).

### Read the estimate

The estimate sits on the right of the bar once an engine is picked: a short line with the time, the memory (a cloud model has none) and, on a window 1280 pixels wide or more, the minutes of quota or, for admins, the cost. Hover it for the detail. It follows your changes half a second after you stop, once the project is saved: until then it reads "The estimate updates once the project is saved." and, while it computes, "Estimating…". The detail has these lines:

- **Scope.** The shots and variants and the resolution: "2 shots × 2 variants in 832×480".
- **Time.** "Time ≈ 4 min on MiniMax H3 (measured on 3 takes)". It comes from the takes already made with the same preset, engine and resolution, whose real durations were measured: that is the calibration. With none yet it reads "Time: — (no measure yet on MiniMax H3)" and the bar shows "—". It fills in after a few generations, and a measure only serves the backend that made the takes.
- **Memory.** "Memory ≈ 22.5 GB, 16.0 GB free on Local Generation". It is an estimate from the size of the model files, never a guarantee. "Memory: unknown" when it could not be estimated.
- **Quota.** Your monthly Video Producer GPU minutes: "Quota: 5 min needed, 40 of 60 min left this month", "Quota: exempt" if you are exempt, and "Cloud: no GPU quota used" for a cloud model, which does not use them. It shows as **GPU quota** in the status bar when your admin set a limit. When your minutes are limited, the minutes of a take are reserved when it is created and adjusted to its real duration when it ends; a take that fails or is cancelled gives them back. With no limit, or if you are exempt, no minute is reserved or adjusted. Until a preset has been measured, each second of video counts for 10 seconds of GPU.
- **Cost.** Admins only, for a cloud model: "Cost ≈ $0.84", or "Cost: unknown for this model" when the provider publishes no price.

### Blocks and warnings

What blocks **Generate selection** (the button is disabled and the bar shows the first reason; hover it to see them all):

- no valid range;
- neither a global direction nor a shot prompt in the range;
- an empty shot prompt in the range;
- a 3D output mode with no up-to-date reference video for the shots of the range (render them in **3D scene**);
- **3D render + AI** with a preset that has no reference mode: ask your admin for a MiniMax-H3 preset that has it;
- no engine, or an engine that is no longer available;
- a preset that is missing or no longer assigned to you ("This preset is missing or no longer assigned to you.");
- a profile the engine cannot generate ("Wan 2.1 / 2.2 cannot generate the Ref2VA profile: switch to FL2VA or to MiniMax H3.");
- model files your admin has not installed ("Models to install for this preset: …"): ask your admin;
- a cloud engine without a model ("Pick a cloud model for this engine.");
- a Ref2VA shot with no reference that can be sent ("“Shot 2” has no reference: Ref2VA needs at least one for this shot.");
- a spent quota ("GPU quota exceeded: 5 min needed, 2 min left this month."): switch to a cheaper quality, a shorter range or a cloud model.

The buttons of a single shot (on a Storyboard card, in the Inspector, in the viewer) do not wait for the estimate, but your admin's server applies the same rules and the page shows the first reason in a message.

What only warns, without blocking:

- a memory estimate above what the GPU has: "Will stream through host RAM, slower." The weights pass through the server's memory. The generation goes on, more slowly, and fails if the server lacks the memory for it (chapter 18);
- the FL2VA profile with no frame linked to a shot: "“Shot 2” has no linked frame: it will be generated from text only." The generation goes on from the text, and the card of the take says "text only". When the shot has a previous shot with a finished take, an icon next to the warning in the Production bar, **Use the previous shot’s last frame**, gives it a first frame (chapter 12);
- an engine that generates from text only, such as the (8 GB) Wan presets, for a shot with linked frames: "This engine generates from text only: the frames linked to “Shot 2” will not be used." The generation goes on from the text;
- a 3D shot changed after its reference video was rendered: "The reference video of “Shot 2” is out of date: render it again in 3D scene." The old video is still sent;
- a 3D reference video on a shot with the FL2VA profile: "“Shot 2” has a 3D reference video, but FL2VA does not read it: choose Ref2VA, or use the start and end frames.";
- a shot longer than the engine allows: "“Shot 2” is longer than this engine allows: it will be cut to 15 s."

Two notes appear only in the estimate tooltip: "Memory use could not be estimated." and "No time measured yet for this engine and resolution."

### Generate

**Generate selection** (Ctrl+G) saves the project and starts one take per shot and per variant, each with its own seed. A shot is built from its shot prompt followed by the filled fields of the global direction, and from its frames and references, according to the profile (see below). If the project could not be saved, nothing starts ("The project could not be saved: generation not started.").

- The single-shot buttons start drafts for that shot only: **Generate** on a Storyboard card, **Generate drafts** in the Inspector and the viewer, and "1 more draft" (or "2 more drafts") in the Inspector, tab **Takes**.
- While takes are in progress, **Generate selection** is refused with "A generation is already running." The bar shows the progress and **Cancel** instead. A shot that has no take in progress can still be started from its own buttons.
- Your admin limits how many generations you can have in progress at once. The takes past that number wait as **Queued** and start by themselves, one by one, as the others end.
- **Add to queue** keeps the current range for later. The queued windows are listed under **Generation queue** in Director IA, tab **Results**, and counted in the status bar. **Generate the queue** starts them and **Clear** empties the list. This list lives in your page: it is not saved with the project.

### Follow the takes

- Each take shows its state: **Queued**, **Generating** (with the step and the percentage), **Failed**, **Cancelled**, or, once finished, its duration. The bar shows the step and the progress of the whole batch, the Storyboard card shows the progress of its shot, and **Window › Background tasks** counts the takes in progress ("2 takes in progress").
- When a batch ends, a message tells how many takes are ready ("2 draft takes ready") with a **View** button that opens the results, and another how many failed ("1 take failed"). PotionUI also sends the notifications "Video Producer: take ready" and "Video Producer: take failed", so you can leave the page: the generations go on without it, and the takes are there when you come back.
- **Cancel** on a card stops that take. **Cancel** in the bar, or **Production › Cancel the generation**, stops all the takes in progress ("Generation cancelled"; "No generation running." if there are none). The GPU minutes they reserved are given back.
- **Retry** on a failed card starts a new take for the same shot, with the same seed, quality and engine. The failed take stays in the list.

### Profiles per preset

The **Project H3 profile** (Director IA, tab **Direction**) says what guides the generation. What an engine can do depends on its preset, and the page greys the profiles it cannot run.

| Profile | Wan 2.1 / 2.2 and its (8 GB) presets, LTX-2 / 2.3, LTX-2.5, cloud models | MiniMax H3 | MiniMax H3 Fast and VDN, MiniMax H3 (12 GB), MiniMax H3 Fast (12 GB) |
|---|---|---|---|
| FL2VA | Yes | Yes | Yes |
| Ref2VA | Greyed | Yes | Greyed |
| Hybrid AV | Greyed | Yes | Yes |

- A greyed profile carries a badge such as "Ref2VA · Hybrid AV: MiniMax H3 only", with the explanation "Wan 2.1 / 2.2 cannot generate Ref2VA, Hybrid AV: reference images (Ref2VA) and generated sound (Hybrid AV) need MiniMax H3." In the **References** tab, "Not sent with this engine" tells you that the engine ignores the references ("References are sent only with the Ref2VA profile on MiniMax H3; Wan 2.1 / 2.2 ignores them.").
- **FL2VA** uses the frames linked to the shot: a start and an end frame give a take "first and last frames", a start frame alone "first frame", and no frame "text only", with the warning above. Chapter 12 shows how to take the first frame from the previous shot.
- **Ref2VA** sends the references of the shot, then the global ones, to MiniMax H3: up to 9 images, 3 videos and 3 audio files.
- **Hybrid AV** works like FL2VA on MiniMax H3, whose model makes the picture and the sound together. The track that drives the performance (Advanced workshop) is not sent (chapter 17).

## 9. Takes and final

A take is one generated video for one shot. Its video is an ordinary PotionUI generation: it stays in your generation history (the gallery), even if you delete the take here.

- Drafts are made at the resolution your admin chose (832×480 unless changed) or the closest the engine offers. The frame rate of a take is set by the preset (Wan 16 fps, MiniMax H3 24 fps). The timeline and the exports use the frame rate of the project.
- Several variants are made per shot: A, B, and so on. A new generation for the same shot goes on with the next free letters (C, D…), separately for drafts and finals; **Retry** and **Make final** keep the letter of the take they come from. They are listed in the Inspector, tab **Takes** (as **Final** and **Drafts**), and in Director IA, tab **Results**, grouped by shot.

### The take card

- The thumbnail carries the letter of the take. Click it to preview the take in the viewer ("Preview take A"); **Back to the sequence** brings you back.
- The first line says "Draft", "Final" or "Final · upscale", then the state ("Queued", "Generating", "Failed", "Cancelled") or, once finished, the duration. The next lines give the profile and how the shot started ("FL2VA · first and last frames", "FL2VA · text only", "FL2VA · first frame", "Ref2VA · references"), the resolution and, for a final, the take it comes from ("from A"), the seed ("Seed 123456") and the engine that made it (the preset or the model, then the backend).
- A queued take shows only its state ("Queued") above an empty line; a take that is generating shows the step, the percentage and a progress bar. When it fails, it explains in your language the usual causes, for example "The server’s GPU ran out of memory: try a lower resolution or fewer frames." (28 known causes are explained); for any other cause it shows the reason that PotionUI gives (in English) or, when it gives none, "The generation failed (invalid_request)." with the code.
- **Compare** puts the take beside a second one in the viewer, both playing in a loop ("Pick a second take to compare"). **Keep** (the star) and **Reject** (the thumb down) flag the take; click again to remove the flag. The export warns about a shot whose take is flagged Reject. **Extract a frame at the playhead** (the image button of a finished take) saves one image of the take as a first or last frame of the shot (chapter 12). **Generation details** opens PotionUI's window about the generation. **Delete** asks "Delete this take?" ("Take A of “Shot 2” leaves the list. The video stays in your generation history.").
- A capture of take cards, in the dark and light themes of the English interface, is in `docs/screenshots/takes-cards.png`.
- On a take in progress, **Cancel** stops it. On a failed one, **Retry** starts a new take.

### Choose a take

**Choose** puts the take on the shot: it plays on the timeline, the shot becomes Draft or Final, and the card shows a check mark and **Used**. Only one take is chosen per shot. The first draft that finishes for a shot that was still "To generate" is put there for you, and so is a finished final. In the viewer, a take previewed outside the cut has **Use this take**. **Assemble chosen takes** (Results tab) puts all the chosen takes in the cut; without any it says "First choose takes for the shots."

### Make final

**Make final** on a draft card (also the button of a Storyboard card, **Make take A final** in the Inspector, **Shot › Make take final** and Ctrl+Shift+G) opens the window "Make final · Shot 2 · A" with the line "Draft in 832×480 · seed 123456". It offers two ways:

- **Upscale** is the default. The engine enlarges the take as it is: the picture and the motion do not change, and it is the fastest way. Wan, LTX, MiniMax H3 Fast and VDN, MiniMax H3 (12 GB) and MiniMax H3 Fast (12 GB), and cloud takes go through SeedVR2 ("SeedVR2 enlarges this take as it is: fastest, the motion does not change."); a take of the base MiniMax H3 preset uses the upscale mode of its own preset ("MiniMax H3 enlarges this take with its own upscale mode: the motion does not change."). Pick the **Target resolution**: 720p, 1080p, 1440p or 4K (the window starts on the resolution of your project), then click "Upscale to 1080p".
- **Re-render at full resolution** generates the shot again at the largest resolution of the engine, with the same seed: "slower, the result may differ slightly."

When no upscaler is assigned to you, the window shows the badge **Upscaler not available** and the explanation "Upscaling this take needs SeedVR2: ask an administrator to install it, or render the take again at full resolution." (the **Make final** button of that take card shows the same sentence as its tooltip), the resolutions are greyed and only the re-render is offered. A take of the base MiniMax H3 preset does not need SeedVR2, as long as its preset is assigned to you. An upscale takes time: on a 12 GB graphics card, the upscale of a 5-second Wan draft to 1080p took about two and a half hours. A capture of this window, in the dark and light themes of the English interface, is in `docs/screenshots/make-final.png`.

The new take is a **Final** one ("Final" or "Final · upscale") that says which draft it comes from ("from A"). You get "Upscale to 1080p started" or "Render at 1280×720 started", the final appears on the card list when it ends, and it is put on the shot ("Final version ready and applied to the shot"). A final uses GPU minutes like any take and is checked against your quota.

## 10. Assistant

The assistant is the PotionUI chat, working in its own mode for this page, **Video Producer assistant**. It reads your project and has four tools, the actions it can run: write the prompt of a shot, fix the contradictions between the global direction and the shot prompts, cut your synopsis into shots, and check the continuity between shots. It proposes and you decide: for the three tools that write or propose something, the chat shows an approval card with a preview, and nothing happens in your project until you click **Approve**.

### Before you start

- Your admin has to configure a language model in PotionUI (Admin › LLM / Assistant) and assign it to you. It must be able to call tools, and a local model server set up for the assistant (llama.cpp `llama-server` or Ollama, with the settings of the administration guide) or an online provider such as OpenAI is the safer choice: the model built into PotionUI ran out of memory, or was too small to call the tools, on a 12 GB graphics card in our tests. Without a model the chat says that it is unavailable (see "If it does not work" below).
- The assistant reads your project as the page shows it, but it writes into the project as saved on the server. Wait for "Saved at" in the project bar before you approve a change.
- Keep the Video Producer page open while you chat: the assistant only knows your project while the page is open on it.

### Open the assistant

Click **Assistant** in the project bar, choose **Window › PotionUI assistant**, or press Ctrl+J (⌘J on a Mac). The chat opens over the page. On a new conversation, the mode chip in its header reads **Video Producer assistant**. A conversation keeps its mode for good ("Mode is fixed after the conversation starts"): if the chat shows a conversation started elsewhere in PotionUI, its header says "Started in …" and offers **start a new chat**.

### What the assistant sees

With each message, the page sends the assistant a summary of your project:

- the project: its name, its saved version and its prompt language;
- where you are: the workspace, the playhead (and the shot under it), your selection and the range;
- the synopsis and the global direction: the five fields and the H3 profile;
- the shots in timeline order: name, start and end, stage, whether a take is on it, whether it has a first and a last frame, and the beginning of its shot prompt;
- the conflicts that the page flags between a shot prompt and the direction, and the color and identity matches it measured between neighbor shots;
- the state of the production: target, mode, quality, progress and queue.

The summary is text and it is kept short: 40 shots at most, 800 characters of the synopsis, 240 of each field of the direction and 160 of each shot prompt, so a longer text is cut in what the assistant reads. It holds none of your images, videos, takes, references, audio or 3D scenes, and the assistant sees no picture. If you leave the Video Producer page, the summary stops: the assistant says the page is not open and asks you to open a project.

### Four requests to try

You write to the assistant in your own language. The examples below are only examples; select a shot first and the assistant knows which one you mean.

#### Request 1: write the prompt of a shot

For example: "Write the prompt of the shot “The gulls”: a low angle on the water, backlit."

1. The chat shows a card **Write shot prompt**, marked **Needs approval**, showing the prompt now and the new text (only the new text when the shot has no prompt yet).
2. Click **Approve**. The new text becomes the shot prompt of that shot (the prompt is created when the shot had none). The page updates at once and says "Prompt of “The gulls” updated by the assistant"; the card turns to **Applied**.
3. Click **Reject**, with a reason if you like, to leave everything as it was.

#### Request 2: fix the contradictions with the direction

When the Direction tab of Director IA shows **To check · N** (for example "The global direction excludes neon lights." under a prompt that asks for neon), ask: "Fix the conflicts between my direction and my shot prompts."

1. The card **Fix conflicts** shows one block per shot to rewrite, with the old text and the new text.
2. **Approve** applies all the rewrites in one change, and the page says "2 prompts rewritten by the assistant". **Reject** applies none: it is all or nothing.

#### Request 3: cut the synopsis into shots

For example: "Cut my synopsis into shots of about 5 seconds." You can also tell a story in the chat and ask for the cut.

1. The card **Split synopsis** lists the proposed shots, each with its time range and "name: beginning of its prompt". It proposes 1 to 24 shots of 2 to 15 seconds, with names of 34 characters at most.
2. **Approve** does not change your project yet. The page opens the **Storyboard** and says "3 shots proposed in Storyboard". The **Proposed breakdown** list (the same one as **Propose a breakdown**) shows the shots: untick the ones you do not want (**Keep shot 1**), rename them, then click **Add 3 shots at the end**. The shots join the end of your film as shots "To generate", each with its shot prompt, and the page says "3 shots added to the storyboard".
3. **Close the proposal** drops it. A new proposal replaces the previous one.

#### Request 4: check the continuity

For example: "Check the continuity between my shots and tell me what to fix." The button **Ask the assistant to check continuity**, in the Direction tab, types this request for you. This one only reads your project, so there is no card.

1. When the assistant has answered, the page says "2 continuity points to check" (or "Continuity checked: nothing to fix"), with a **Show** button when the Direction tab is not on screen.
2. In **Director IA**, tab **Direction**, a **To check** section, with "Assistant · 14:32" beside its title (the time of the check), lists the pairs of neighbor shots to look at, as "Shot 1 → Shot 2". Click a pair to go to the shot. Under each pair, a line says what is wrong and a second line how to fix it. A dot on the tab **Direction** says there is something to check.
3. What it looks for: a shot without a prompt; a shot prompt that contradicts the global direction; a shot shorter than 2 s or longer than 15 s; a shot with the FL2VA profile and no first frame; a camera move that changes between two shots; a jump of brightness or color temperature (the page measures these on the images, the seam frames of the shots when they have some and their thumbnails otherwise, and the line carries the badge **Measured**; chapter 12); and a similarity point between two takes. That last one comes from the similarity score, which stays simulated (chapter 17), so its line carries the gray badge **Simulated** instead. Shots that come from a source are skipped.
4. **Dismiss the check** (the cross of the section) removes the list. Ask again to refresh it.

### Suggestions that fill the request for you

Three places of the page start the chat with a request already typed. You can read it, edit it, then press Enter: nothing is sent for you.

- **Ask the assistant to check continuity** (Director IA, tab Direction): "Check the continuity between my shots and tell me what to fix."
- **Ask the PotionUI assistant**, in the **Prompt library & assistant** window. The window closes first. The request depends on what the window was writing into: "Help me write the prompt of the shot “The gulls”.", "Help me write the prompt at 5.0 s.", "Help me write the “…” field of the global direction." or, with no target, "Help me write a prompt for this project."
- **Ask the assistant**, in the Sound design workshop, for example: "Help me write a sound brief: Ambience, from 0.0 s to 5.0 s."

If you had already typed something in the box of the chat, your text stays and the suggestion is not added. If your PotionUI is too old to fill the box, the chat just opens with an empty box and you type the request yourself. The suggestions are written in the language of the interface.

### What it changes, and what it does not

- It writes shot prompts (requests 1 and 2) and proposes shots (request 3). It never starts a generation, chooses a take, makes a shot final, adds, moves or deletes a shot by itself, nor edits the synopsis, the global direction, the references, the titles, the audio or the 3D scene. For a field of the direction or for a sound brief it answers in text only: copy what you like yourself.
- **Propose a breakdown** and **Production › Split synopsis into shots…** are not the assistant: they only cut the synopsis into sentences, one shot per sentence. **Production › Continuity check** takes you to the Direction tab and does not call the assistant.
- Each approved change is a new version of your project: **File › Version history…** shows it with the word "Assistant". When the page applied the change itself, **Edit › Undo** works on it like on your own changes.
- If you had typed in the same shot prompt and not yet saved it when you approved, the page reloads the project to show the assistant's version ("Project reloaded with the assistant’s changes"): that typing and your undo history are lost. Wait for "Saved at" before you approve.
- The assistant writes shot prompts in the prompt language of the project (chapter 15) and answers you in your language. It never translates what you wrote. The contradiction checks only read texts in the prompt language.
- The list **To check** and the proposal appear once, when the answer arrives. They disappear when you leave the page or open another project, and reopening an old conversation does not bring them back: ask again.

### If it does not work

The chat itself is a PotionUI window: its buttons (**Tools**, **New chat**, **Approve**, **Reject**, **Retry**) keep PotionUI's labels.

- **"Chat is currently unavailable".** No language model is assigned to you. Ask your admin to add one in Admin › LLM / Assistant and assign it to you. (An admin reads "No enabled LLM configurations" instead.)
- **The assistant answers but never shows a card, or says it cannot act.** The **Tools** button of the chat box is off: hover it, it reads "Tools OFF"; click it to turn the tools on, and check that the four tools of the group Video Producer are ticked in its list. Your admin may also have turned them off for the model, or the model may not be able to call tools: try another one.
- **The assistant does not seem to know your project, or the header says "Started in …".** The conversation was started in another mode. Click **start a new chat** from the Video Producer page.
- **The assistant says the page is not open on a project.** Open a project in Video Producer, keep the page open and ask again.
- **A card is Failed and quotes `version_conflict`, `project_not_found` or `shot_not_found`.** The project was saved from somewhere else at the very moment of the save, was deleted, or no longer has that shot. Let the page reload the project (**File › Open…**), then click **Retry** on the card or ask again. The assistant says so itself in the chat.
- **You approved and the chat says "The assistant changed another project, not the one open here."** The answer was for another project than the one you have open now. Open that one, or ask again here.
- **"The project could not be reloaded. Reopen it to see the assistant’s changes."** The assistant's change is saved, but the page could not reload it: open the project again (**File › Open…**).
- **The suggestion did not appear in the box.** You had already typed a draft, or your PotionUI cannot fill the box (it then opens it empty). Type or paste the request.
- **A prompt came out in the wrong language.** The assistant follows the **Prompt language** of the project, in **Project properties…** (chapter 15). Change it, then ask again.
- **The assistant ends with an out-of-memory error, answers in text only or never shows a card.** If your admin connected the model built into PotionUI on a 12 GB graphics card, it can run out of memory or be too small to call the tools. Ask your admin to connect llama.cpp `llama-server`, Ollama or an online provider (chapter 1).
- **The chat shows "Ollama returned status 400: request (… tokens) exceeds the available context size".** The model is connected through Ollama with its default context, which is too small for the assistant. Ask your admin to set the **Context Size** of the Ollama configuration to 16384.
- **The assistant waits about ten seconds before every answer, or sometimes ends without a card.** The model thinks before each call, or is loaded again at every turn. Ask your admin to turn its thinking off (**Reasoning Effort** None for an OpenAI configuration, **Thinking Mode** Automatic or Disabled for Ollama) and, for Ollama, to set **Keep Alive**.

## 11. Prompts: library and composer

The window **Prompt library & assistant** opens from **Window › Prompt library**, or from the **Library & assistant** links placed near a text (in the fields of the global direction, in the Inspector for a shot prompt and in the window that edits a shot prompt). It writes into a target, shown under its title: one of the five fields of the global direction, or a shot prompt. Opened from the menu it has no target and copies the prompt to the clipboard (**Copy the prompt**). The window has two tabs, **Library** and **Composer**, and a link, **Ask the PotionUI assistant**, that closes the window and opens the PotionUI chat with a request already typed (chapter 10). The names, descriptions and categories of the templates and the choices of the composer exist in English and in French and follow the language of the interface; the texts they insert follow the prompt language of the project (chapter 15).

- **Library.** Five libraries, **Built-in**, **Personal**, **Project**, **Favorites** and **History**, and nine categories (Cinema, Camera, Lighting, Film styles, Dialogue, Photography, Sound, Continuity, To avoid). Search by name, description or keyword; the star marks a favorite. Each template says which H3 profiles it suits. A template can have variables, such as the subject or the place, that you fill in before inserting it. The **Editable preview** can also be edited by hand. **Save to Personal** keeps your version, and every inserted text goes to **History**. A new project starts with the built-in templates and one personal template; **Project**, **Favorites** and **History** are empty until you star a template or insert a text.
- **Composer.** Builds a prompt from four parts, **Camera movement**, **Lighting**, **Film style** and **Dialogue or acting intent**, for the H3 profile you pick (it starts from the profile of the project). Choose one option per part, or type your own in **Other…**, and fill in the subject, the action, the place and the emotion. The **Final prompt** stays editable, and **Recompose from the choices** brings it back. **Required references** tells whether the range has what the profile needs. When a Control video covers the range, the camera part is **Set by the Control video** and locked.
- **Insert** writes the text into the target: **Add to the text** adds it to the existing text, **Replace** replaces it.

The three H3 profiles and what each one asks for on the range:

| Profile | Meaning | It asks for | Engines |
|---|---|---|---|
| FL2VA | Continuity between the start and end images. | Start and end frames in the range. Without any frame, the shots are generated from text only. | All of them. |
| Ref2VA | Keep the identity of the references during the action. | An identity reference (character, object). The generation follows your references. | MiniMax H3 only (not its Fast and VDN variants, nor the (12 GB) presets). |
| Hybrid AV | The soundtrack, rhythm and dialogue drive the picture. | An existing audio track in the range (dialogue or music). | MiniMax H3, Fast and VDN, and the (12 GB) presets. |

The engine, not the table, has the last word: the page greys a profile the chosen engine cannot generate (chapter 8). The audio tracks of the project are not sent to the engine: MiniMax H3 makes the sound itself, and the track that drives the performance is one of the settings that the engine does not use (chapter 17).

When a Control video is present, the motion comes from the guide.

## 12. Color and continuity

Continuity is about the seams, the cut from one shot to the next. Video Producer measures the color of every seam, warns when two neighbor shots do not match, fixes the color in one click, and can start a shot from the exact image where the previous one ended.

### Color match

An alert appears only when two neighbor shots do not match: "“Shot” is brighter, darker, warmer or cooler than the previous shot". It shows in Director IA (tab **Direction**, under **To check**), in the Storyboard (under **Continuity**, and as a warning icon on the card of the shot) and in the Inspector. **Match** (**Match color** in the Storyboard) fixes it in one click by adjusting exposure and temperature to the previous shot. The **Color** tab also has the luminance scope, six presets (Original, Golden light, Cold morning, 35 mm film, Blue night, Soft) and fine settings (**Exposure**, **Contrast**, **Saturation**, **Temperature**), with **Reset** and **To all shots**. Before a shot has an image, the tab says that color can be adjusted once the shot is generated.

The measure is made on real images, for each shot that has one. The starter project has none yet, and the Storyboard then says "No match to check yet: the shots have no image." A similarity percentage between two generated shots can also appear in the alerts ("Check the identity between … and … (similarity 78 %)"): it is simulated (chapter 17). Color is real.

### What the measure looks at

For each pair of neighbor shots the page compares the end of the first with the start of the second:

- for the previous shot, its **Last frame** image if it has one, otherwise its thumbnail;
- for the shot, its **First frame** image if it has one, otherwise its thumbnail.

Any image that you placed as a first or last frame counts, not only the images made in this chapter. The assistant's continuity check (chapter 10) marks the points that the page measured with the badge **Measured**; hover it to see what was measured: "Measured by this page on the seam frames: last image of the previous shot, first image of this one", or "Measured by this page on the shots’ thumbnails". The similarity point keeps the gray badge **Simulated**.

### Start a shot from the previous shot

A **seam frame** is an image taken from a take and set as the first or last frame of a shot. With the FL2VA profile a take starts on its first frame (chapter 8), so giving a shot the last image of the previous shot makes the two shots join without a jump.

**Use the previous shot’s last frame** is offered in five places:

- under each alert of Director IA, tab **Direction**, section **To check**, next to **Match** or **See takes**;
- under each alert of the Storyboard, section **Continuity**, next to **Match color**;
- on the lines of the assistant's check that say that a shot has no first frame (chapter 10);
- in the **Frames** section of the Inspector, tab **Shot**, which shows the **First frame** and the **Last frame** of the shot ("None" when empty) and a button of the same name;
- as an icon next to the warning of the Production bar that says that the shot will be generated from text only (chapter 8).

When you click it:

1. The page saves the project and asks the server for the last image of a take of the previous shot: the take chosen for that shot or, if none is chosen, its most recent finished take. The button reads "Extracting the image…" meanwhile.
2. The image is saved in your library as a PNG, added to the media of the project and set as the **First frame** of the shot, with full influence, at the start of the shot. You see it in the **Frames** row of the timeline and in the Inspector. The page says "Last image of “Shot 1” set as the first frame of “Shot 2”" with an **Undo** button.
3. Nothing is generated and the takes you already have do not change: the next take you generate for the shot starts from that frame. The frame only guides the generation; it is not drawn into an exported video.

If the shot already has a first frame, a window asks "Replace the first frame?" ("“Shot 2” already has a first frame. The new image replaces it; you can undo."). **Replace** swaps it and **Keep the current one** changes nothing. The replaced image stays in the media of the project. **Undo** in the message, or **Edit › Undo**, brings the previous frame back.

The action is greyed, with the explanation "“Shot 1” has no finished take yet.", while the previous shot has no finished take with a file, and it is not offered for the first shot of the film.

### Extract a frame at the playhead

For another moment than the last image, use **Extract a frame at the playhead**, the image button on the card of a finished take (Inspector, tab **Takes**; Director IA, tab **Results**). Its tooltip says "Saves the image of this take under the playhead as the first frame (first half of the shot) or the last frame (second half)". Put the playhead on the shot, at the moment you want, then click it:

- the image is taken from that take at the position of the playhead in the shot (for the take that the shot plays, its in point is taken into account);
- in the first half of the shot it becomes the **First frame**, in the second half the **Last frame**; a playhead outside the shot counts as its start or its end;
- the page says "Image at 2.5 s set as the first frame of “Shot 2”" (or "last frame"), and asks "Replace the last frame?" first when there is one.

### Other checks

The assistant can run more checks on request: shots without a prompt, contradictions with the global direction, durations outside 2 to 15 s, FL2VA shots without a first frame and camera moves that change between two shots, together with the color points above. Its answer is a second **To check** list in the Direction tab (chapter 10).

## 13. Audio and subtitles

Audio lives in tracks, each with a role: Dialogue, Music, Ambience or SFX. **Audio › Add audio track** and **Audio › Import audio file…** bring sounds in; **Audio › Mixing console** shows the console. In the console each strip has a role, effects (**Equalizer**, **Compressor**, **Filter**; **+ effect** adds one), sends to the reverb and delay buses (R and D), pan, a fader (double-click it to go back to 0 dB), a meter, **M** and **S** and an automation button; the auxiliary buses and the **Master** follow. The pills at the top show one role only. **Voice and dialogue…** and the sound design commands (**Ambience…**, **Foley…**, **Texture…**, **Impact…**, **Musical intent…**) open the **Sound design workshop**, which is simulated (chapter 17). The text of a dialogue is real: it feeds the subtitles, together with the titles of the timeline (chapter 14).

The four tracks of a new project are empty. **Audio › Import audio file…** brings in your own audio files (chapter 6). The console plays them for real: the faders, mute and solo, pan, equalizer, compressor, filter and sends act on the sound you hear, the meters show it, and the clips of the timeline draw the waveform of the file. The sounds that the Sound design workshop prepares are still synthesized by your browser (WebAudio).

## 14. Exports

**File › Export video…** (Ctrl+E) opens **Export and share**, with three tabs: **Video**, **To other software** and **Subtitles**. **File › Export to other software…** (Ctrl+Shift+E) and **File › Export subtitles…** open the other two. Before the export, the window warns about shots that are not final yet, shots that use a take you flagged **Reject** and direction conflicts that are not solved. Every export starts by saving the project; if that fails, the page says "The project could not be saved: nothing was exported." and exports nothing.

### Video

Pick a format, a resolution and the extent, then click **Export**.

- **Format.** Two formats are real. **Web · H.264 MP4** has the aspect ratio of your project. **Social media · vertical H.264** is always 9:16: the shots fill the frame and are cropped around their center. **Master file · ProRes 422** and **Archive · H.265** stay simulated and carry the badge **Simulated**.
- **Resolution.** 720p, 1080p or 4K; the window starts on the resolution of your project. The short side of the picture is 720, 1080 or 2160 pixels. For a 16:9 project a web video is 1280×720, 1920×1080 or 3840×2160, and a social video is 720×1280, 1080×1920 or 2160×3840.
- **Extent.** The web and social videos always render the **Whole sequence**. **Range** is greyed, and when you have drawn a range the window says "Web and social exports render the whole sequence."
- **Audio stems by role.** The switch is simulated and does nothing for the web and social videos.

Under the choices the window shows the name of the file (the project name with spaces turned into underscores, then the resolution, for example `Dawn_at_the_harbour_1080p.mp4`), its frame rate and aspect ratio and the note "Rendered on the server with ffmpeg".

What the video holds:

- The shots in the order of the project, with the **Color** settings (exposure, contrast, saturation, temperature) and the fades of each shot. A shot with no file that the server can find, and every gap between shots, is black and silent. An image placed as a shot is held for the length of the shot.
- The sound of each shot's own video (the viewer does not play it, but the export keeps it), and your audio tracks with their gain, the fader of their track, mute and solo, and their fades. The tracks are added together as they are, without automatic leveling.
- Not in the video: the titles and markers, the subtitles (always a separate file, see below), and the pan, equalizer, compressor, filter, sends, automation and master fader of the console. What you hear in the console with those is not what the file holds.

If your admin has not installed ffmpeg on the server, the Video tab says "ffmpeg is missing on the server: web and social exports need it." (with a **Read the guide** link for an admin, and "Ask an administrator to install it." for anyone else) and **Export** is disabled for the web and social formats.

### Follow the export

The export runs on the server, in the background. The window shows a card with the file name, its state (**Queued**, **Rendering**, **Ready**, **Failed** or **Cancelled**), the current step, a percentage and a progress bar:

| Step | What happens |
|---|---|
| Waiting in the queue | Another export is running on the server, which makes one at a time. |
| Assembling the shots | The shots are put end to end, with their color and fades. |
| Mixing the audio | The sound is mixed. This is the same run as the assembly: the step changes at 50 %. |
| Converting to MP4 | The final MP4 is made. The percentage goes from 70 to 95 % during this step. |
| Saving to your library | The MP4 is copied into your library. |

- **Cancel** stops a queued or running export ("The export was cancelled."), at any step.
- You can close the window or leave the page: the export goes on. With the window closed the page keeps following it and shows a toast with **Download** when it is ready. PotionUI sends the notification "Video Producer: export ready" (or "Video Producer: export failed"), and when you open **Export and share** again the card is back.
- A project has one export at a time ("An export of this project is already running.").
- When it is ready the card says "Dawn_at_the_harbour_1080p.mp4 is ready" with its size, and offers **Download** and, when your PotionUI can show it, **Show in the library**, which opens your library on the videos. The MP4 is also in your library like any video, so you can import it into a project (chapter 6).
- A failed export says what failed ("ffmpeg could not assemble the video.", "The video could not be converted." or "The video could not be saved to your library.") and, under it, the technical message of the server (chapter 18).

### Previous exports

Under the card, **Previous exports** lists the export in progress first, with its state, then the earlier exports of the project: format and resolution, state, when it ended and its size, with a download icon (**Download <file>**) and a trash icon (**Delete <file>**). Deleting asks "Delete this export?" ("<file> is removed from the export folder. The copy in your library stays."): **Delete** or **Keep it**. With none, the list says "No video exported for this project yet."

The MP4 files are kept in your PotionUI storage, in a `video_producer/exports/` folder, until you delete them. Your admin sets a size budget for that folder, per user. When it is reached, your oldest finished exports are deleted to make room, and if that is not enough the export is refused: "The export folder is full: delete older exports and try again." The copy in your library does not count in this budget and stays when an export is deleted.

### To other software

Three files, built by the server from your saved project: **FCPXML** (`.fcpxml`), **OpenTimelineIO** (`.otio`) and **EDL CMX 3600** (`.edl`). Click a card, read its note and the beginning of the file, then click **Download** followed by the file name, which comes from the project name (for example "Download Dawn_at_the_harbour.fcpxml"). The page says "<file> downloaded".

- **FCPXML.** "V1 sequence with the chosen takes, shot names and in points." One video row, with a shot without media as a gap. No audio.
- **OpenTimelineIO.** "Video and audio tracks by role; opens in Resolve, Premiere (plugin) and Nuke Studio." The same video row, and one audio track per track of the console, with the position, role and gain of each clip. The audio clips carry no file.
- **EDL.** "Universal edit list (V1 only), for grading or conforming." One event per shot, with its name and its media file; a shot without media is on a black reel (BL).

These files carry the cut only: no fades, no color settings, no titles and no audio files.

**Media paths.** The files point to the real media files of your shots, as the server stores them: "Media paths are the real files on the server, taken from the saved project." The preview shown in the window lists file names, but the file you download holds the full paths on the server. If your editing software runs on another computer, those paths do not exist there: put the videos of your takes (download them from your gallery) and your imported media on that computer and relink them in your software.

**Importing.** Editing software that reads FCPXML 1.10 imports the `.fcpxml`: the project appears in an event named "Video Producer". The `.otio` file opens in the software named above and in other software that supports OpenTimelineIO. The `.edl` is read by editing and grading software that support the CMX 3600 format. Menus differ between software and between versions: follow the import command of yours.

### Subtitles

An SRT file built from the dialogue text (the lines written for the audio clips, with the name of the character in front: "Mara: Hello") and from the titles of the timeline (the title, then its subtitle on a second line), in time order. The tab lists the cues with their times ("No dialogue or title to subtitle." when there is none) and offers **Download** followed by the file name, which ends in `.srt`. The subtitles are never burned into the video: load the SRT in your player or your editing software.

## 15. Language

Video Producer exists in English and in French. Choose **English** or **Français** in **Video Producer › Preferences…**, setting **Language**, or click the `EN` or `FR` reminder at the left of the status bar, which opens the same window. The change is immediate and is saved for you alone, on the server; if the saving fails, a message says that the language changed for this session only. Until you choose, the page follows the language of your browser (French if it is French, English otherwise).

The **Preferences** window has five other settings: **Prompt language** (see below), **Preview quality** (**Best performance**, **Balanced** or **Best quality**, without effect), **Snapping by default**, **Framing guides** and **Single-key shortcuts** (chapter 16). Except **Prompt language**, which is saved with the project, they apply to the current session and are not saved.

What is translated: the menus, the windows, the buttons, the tooltips, the messages, the names given to new items (for example a new shot or a new track), the prompt library with its templates, categories and composer choices, and the way numbers and durations are written. What is never translated is the content of your project: your own texts (the synopsis, the global direction, the shot prompts, the names and titles you typed, the project name) and the starter project, which is created once and is not translated afterwards. Product terms such as Director IA, Storyboard, Control video or FL2VA are the same in both languages.

### Prompt language

Each project has its own **Prompt language**, English or French. It is the language of the texts that are sent to the models, the global direction and the shot prompts, and it does not depend on the language of the interface. It is English by default.

Change it in **Project properties…** (the setting says "Language of the direction and prompts sent to the models. Changing it does not rewrite existing text.") or in **Preferences…** (the setting says "Applies to the current project"). It is saved with the project. A new project always starts in English, whatever the language of the interface or of the project that is open.

What it changes:

- **The starter project.** Its global direction and its shot prompts are written in English, even when the interface is in French. Its name, synopsis, shot names, title and marker follow the language of the interface.
- **The prompt library.** The text that the built-in templates insert, their placeholders (the subject, the place and so on) and the default values of those placeholders are written in the prompt language. The names, descriptions and categories of the templates follow the language of the interface.
- **The composer.** The **Final prompt** is composed in the prompt language. The choices you click keep the language of the interface.
- **The direction checks.** The checks that read your texts use the rules of the prompt language: the contradictions between the global direction and a shot prompt (for example a direction that excludes neon and a prompt that asks for it), and the camera instructions in a prompt that a Control video covers. A text written in the other language is not checked.
- **The assistant.** It writes every shot prompt, rewrite and proposed shot in the prompt language of the project, and answers you in your own language. The contradiction checks it runs use the rules of that language.

What it never changes: nothing you typed is translated, and changing the setting rewrites no existing text. Set the language before you write, or rewrite the texts yourself.

## 16. Keyboard shortcuts

The table gives the shortcuts for Windows and Linux. On a Mac, read ⌘ for Ctrl, ⌥ for Alt and ⇧ for Shift; the menus and the tooltips show the notation of your system, and the side panel is ⌃⌘1 (Control and Command). **Search commands…** (Ctrl+K) finds any command, and **Keyboard shortcuts** (Ctrl+/) lists those that have a shortcut. The menus, the command search and that window show only the shortcuts that work.

| Shortcut | Action |
|---|---|
| Ctrl+K | Search commands… |
| Ctrl+/ | Keyboard shortcuts |
| Ctrl+, | Preferences… |
| Esc | Close, in this order: the command search, the open window, the open menu, a take preview or comparison; otherwise clear the selection |
| Ctrl+Z, Ctrl+Shift+Z | Undo, Redo |
| Ctrl+S | Save |
| Ctrl+O | Open… |
| Ctrl+I | Import files… |
| Ctrl+E, Ctrl+Shift+E | Export video…, Export to other software… |
| Ctrl+G | Generate selection |
| Ctrl+Alt+G | Add selection to queue |
| Ctrl+Shift+G | Make take final |
| Ctrl+J | PotionUI assistant (opens the chat in the Video Producer assistant mode) |
| Ctrl+Alt+1 | Side panel |
| Space | Play / pause |
| Ctrl+B | Split at playhead |
| Ctrl+D | Duplicate |
| Backspace, Delete | Delete |
| A, R, B | Select tool, Range tool, Blade tool |
| I, O | Set in point, Set out point |
| Alt+X | Clear range |
| Alt+[, Alt+] | Trim start to playhead, Trim end to playhead |
| M | Add marker |
| N | Snapping |
| F, U, Alt+Backspace | Favorite, Remove flag, Reject |
| Left arrow, Right arrow | Move the playhead by one frame, 1/fps of the project (1 s with Shift) |
| Left arrow, Right arrow (Storyboard) | Select the previous or next shot |
| Home | Go to the start |

The single-letter shortcuts (A, R, B, I, O, M, N, F and U) can be turned off in **Video Producer › Preferences…**, setting **Single-key shortcuts**, which is on by default. Space, Backspace, Delete, the arrows and Home do not depend on it.

When the shortcuts work:

- Only while the focus is on the page and not in a text field. With a text field focused, a window open (a PotionUI picker or confirmation included) or the command search open, the other shortcuts are off; Esc, Ctrl+K and Ctrl+/ always act. While the PotionUI chat is open, the shortcuts of the page are off.
- A combination acts only with exactly its keys. Ctrl+Shift+I and Ctrl+Shift+J (on a Mac Option+Command+I, J or K) stay with the developer tools of the browser, and the Alt+Left arrow of the browser keeps going back. The page never takes the combinations that manage the tabs and windows of the browser (Ctrl+N, Ctrl+T, Ctrl+W, Ctrl+Tab, Ctrl+1 to Ctrl+9), its address bar (Ctrl+L), its page search (Ctrl+F) or the clipboard (Ctrl+C, Ctrl+V): for the workspaces, a new project or a new title, use the menu, the buttons or the workspace selector.
- A key held down does not repeat a command that switches something (Space, M, N, F, U, Ctrl+S, Ctrl+G, Ctrl+D and the like). Undo, Redo, Delete and the arrows do repeat.
- On a Mac, Ctrl+K in a text field stays with the text editor; the command search is ⌘K. The / of Ctrl+/ needs Shift on some keyboard layouts, such as the French one: the page accepts it either way.

### Keyboard and screen readers

Every button has an accessible name, and an icon button shows its tooltip when it receives the keyboard focus, not only when the mouse hovers it. The Tab key reaches every control with a visible focus ring, including the first choice of a window that you opened with the mouse. The trim and fade handles of the timeline and the camera keyframes are mouse handles that Tab skips: use the **Cut** menu and the Inspector instead (chapters 3 and 7). A screen reader hears the progress of a generation or of an export at each 10 %, or when the step changes, and never more than once every 3 seconds.

## 17. What is simulated

Some parts keep their interface but do not do the real thing. They carry a gray dashed badge, **Simulated**, never a yellow one: yellow is kept for real points to check. **Help › Simulated features** opens the list of the six items below. What the engine you picked cannot do is not a simulation, and it has a plain gray badge instead: a greyed profile ("Ref2VA: MiniMax H3 only"), **Upscaler not available** and **Not sent with this engine** (chapters 8 and 9). In the Advanced workshop that last badge has the same dashed outline as **Simulated**, because the setting it marks stays in your project and changes nothing.

The badge **Simulated** appears in the header of the window **Sound design workshop** (titled **Voice and dialogue** for a voice); next to the formats **Master file · ProRes 422** and **Archive · H.265** when one of them is picked, next to the audio stems and, when a simulated format is picked, in the footer of the **Video** tab of the export window ("Simulated render: master and archive"); on the automation button of the console strips; and on the identity line of the assistant's check (chapter 10).

Everything else works for real: the generation itself (the engines your admin enabled, the estimate, the takes with their progress, cancel and retry, the finals by upscale or re-render, the quota and the notifications), saved projects, **File › Open…**, **File › Version history…** and **File › New project…**, the import of your images, videos and audio files with their thumbnails and their playback, editing on the timeline (trim, fades, split, snapping, range, markers, undo and redo), the selection and the Inspector, the Storyboard (the **Propose a breakdown** button is a simple cut into sentences, not a simulation), the PotionUI assistant with its four tools (chapter 10), the prompt library and the composer, the direction conflict checks, the color match, the 3D scene (scenes built from a picture, imported splats and Blender files, the camera, captures, reference videos and the 3D output modes), the mixing console playing your audio files, the seam frames, the web and social videos (MP4 files that ffmpeg assembles on the server) and the FCPXML, OpenTimelineIO, EDL and SRT files, which are real files.

The window **Simulated features** lists six items. For each one, the table gives what the window says and what is real next to it.

| Item in the window | What the window says | What is real next to it |
|---|---|---|
| **Identity score** | The identity similarity between two shots, in the continuity check and in the assistant’s review, is simulated. The color match really analyzes the images. | The color check analyzes the images for real: the seam frames of the shots and their thumbnails (chapter 12). No identity measure is available to plugins, so the percentage stays simulated. |
| **Lip sync** | No lip sync is computed: the lip sync options of the Sound design workshop and of the Advanced workshop stay in the project and change neither the takes nor the export. | MiniMax H3 makes picture and sound in one pass, so there is no separate lip-sync step. The text of the dialogues feeds the subtitles for real. |
| **Generated voices and dialogue** | The Sound design workshop generates no voice, dialogue or sound: preparing is simulated and what you hear is a simple synthesis in the browser. The dialogue text feeds the subtitles, and imported audio files play for real. | The audio files you import play for real through the console (chapter 13). PotionUI has no speech or sound-effect preset to prepare ambience, foley, texture, impact or music for the workshop. |
| **Console automation and processing** | The Auto button only switches a mode: no automation curve is recorded. Pan, inserts, sends and the master bus are heard in the browser but are not applied to the exported video, which keeps the gain, the track faders, mute, solo and the fades. | The console plays your audio files for real: faders, mute and solo, pan, equalizer, compressor, filter, sends and meters act on the sound you hear. The exported video applies gain, track faders, mute, solo and fades (chapter 14). |
| **ProRes, H.265 and stems** | The master file (ProRes), the archive (H.265) and the audio stems are simulated: no file is written. The web and social MP4 videos and the FCPXML, OTIO, EDL and SRT files are real. | The web and social videos and the FCPXML, OpenTimelineIO, EDL and SRT files are real (chapter 14). PotionUI's video converter writes only H.264 MP4 or VP9 WebM, and no audio is rendered per role. For the simulated formats the window ends with "Simulated render complete: no file is written for this format." |
| **Engine settings with no counterpart in the preset** | The settings marked “Not sent with this engine” in the Advanced workshop stay in the project but do not change the takes: the seed (each take draws its own), the final resolution, steps, CFG, LoRA, windows, consistency, post-processing and the Hybrid AV audio driver, as well as the Hybrid builder weights and the guidance of the Control videos. | What drives a generation is the engine, the quality, the variants and what is in your project: the direction, the shot prompts, the frames and the references (chapter 8). |

The last item gives the main settings. The full list of **Advanced workshop** settings that the engine does not use is: consistency between windows, lock character identity, motion guide first, the generation windows with their length and overlap, the final resolution, the seed, the steps, the guidance (CFG), the LoRAs, the track that drives the performance, lip sync, follow the rhythm of the cut, audio / picture offset, result naming, post-processing and insert variant A automatically. They stay in the project, but they are not sent to the engine and drive no generation: a preset only exposes the controls it declares, and MiniMax H3, for example, has no guidance and no negative prompt. The workshop greys them and marks each one with the badge "Not sent with this engine" (hover it: "The Video Director builds the request from the shots, the direction, the frames and the references; this setting stays in the project but does not change the takes."). **Variants per window** stays active. The Hybrid builder weights and its saved profiles, and the guidance of a Control video, are not sent either, but they are not greyed. The seed of a take is drawn by the server and shown on its card, and the resolutions follow the draft and final rules of chapter 8.

The assistant, for its part, is not simulated: it is the PotionUI chat in the Video Producer assistant mode, which writes shot prompts, fixes conflicts with the global direction, splits a synopsis into shots and checks continuity, and you approve each change before it touches the project (chapter 10). The one simulated point in what it shows is the identity similarity between two takes.

## 18. Troubleshooting

- **The Production bar shows no engine.** The pop-up reads "No engine". Your admin has not finished the setup: an engine, a video preset assigned to you, or a video model turned on for the cloud provider. Ask them to open Admin → Plugins → Video Producer.
- **The estimate shows "—" for the time.** Nothing has been measured yet for this preset, engine and resolution (the calibration is empty). It fills in after a few generations.
- **"Will stream through host RAM, slower."** The memory estimate is above what the GPU has. The generation is not blocked. If the server lacks free memory for it, the engine refuses to start and the take fails (`host_ram_oom`).
- **The quota is spent.** **Generate selection** says "GPU quota exceeded" until the next month or until your admin raises the limit of your plan. Running generations are not stopped, and a take that fails or is cancelled gives its minutes back. The first takes of a preset count 10 seconds of GPU for every second of video, which can look generous until the real durations are measured.
- **Generate selection is disabled.** Read the message in the bar: no range, no direction and no shot prompt, an empty prompt, a 3D mode with no up-to-date reference video, no engine, a preset that is not yours, a profile the engine cannot generate, models to install, a cloud model to pick, or the quota.
- **"Models to install for this preset: …".** Your admin has not downloaded the model files that preset needs. Ask them.
- **A warning says the shots will be generated from text only.** The FL2VA profile has no frame linked to the shot. Add a start or an end frame (**Use the previous shot’s last frame** takes the first one from the previous shot, chapter 12), or pick another H3 profile; the generation is not blocked.
- **A take stays Queued.** Your admin limits how many generations you can have in progress at once: the take starts by itself when one of yours ends. If it stays Queued while nothing of yours is running, tell your admin.
- **A take failed.** The card explains the usual causes in your language (for example "The server’s GPU ran out of memory: try a lower resolution or fewer frames."); for any other cause it shows the reason that PotionUI gives (in English) or, when it gives none, "The generation failed" followed by a code. **Retry** starts a new take for the same shot with the same seed. Typical causes: the GPU ran out of memory (`cuda_oom`: try a draft, a shorter shot or another engine); a model file is missing on the server (`missing_model_file`: ask your admin to download it again); the server ran out of memory while streaming the model (`host_ram_oom`). If PotionUI was restarted during the generation, the take is marked failed and cannot resume: use **Retry**. If every take then fails within seconds after an out-of-memory error, tell your admin: the server may need a restart.
- **"Upscaler not available" in Make final.** No upscaler is assigned to you: SeedVR2 enlarges the takes of Wan, LTX, MiniMax H3 Fast and VDN, the (12 GB) presets and cloud models. Use **Re-render at full resolution**, or ask your admin about SeedVR2.
- **References are ignored with MiniMax H3.** Ask your admin to check the model file picked for the References mode. The engine ignores the references of a profile other than Ref2VA, and of any other preset.
- **I closed the page during a generation.** The takes go on; open the project again to find them. The notifications tell you when they end.
- **The export window says "ffmpeg is missing on the server: web and social exports need it."** The server cannot find ffmpeg, so the web and social videos cannot be made. Ask your admin to install it; once it is, reload the page. The files for other software and the subtitles still download.
- **"No shot has a video file to export yet."** No shot of your saved project has a video or image file the server can find: every shot is still "To generate", or the media were removed from your library or gallery. Generate or import the shots, then export again. A single shot without a file does not stop the export: it is black and silent in the video.
- **"An export of this project is already running."** A project has one export at a time. Wait for it, or click **Cancel** on its card.
- **"The export folder is full: delete older exports and try again."** Your exports have used your size budget. Delete some in **Previous exports** (the copies in your library stay), or ask your admin for a bigger export budget.
- **An export stays Queued.** The server makes one export at a time, for everybody, so yours waits its turn. If it never starts, tell your admin.
- **"Converting to MP4" takes long.** A long sequence at 4K can take many minutes on a small server; the percentage shows how far it is. The export fails with "The video could not be converted." only if ffmpeg stops making progress for 5 minutes. Export at 1080p or 720p to go faster.
- **An export is Failed.** The card says what failed and, under it, the message of the server. "ffmpeg could not assemble the video." can come from a file ffmpeg cannot read, or from PotionUI restarting during the export ("The server stopped during the export."); start it again, and if it fails again give the message to your admin. "The video could not be saved to your library." means that your PotionUI storage is full: free some space and export again.
- **A shot is black or silent in the video.** The server found no file for that shot (media removed from your library or gallery), or the file has no soundtrack. The sound of the console's pan, equalizer, compressor, filter, sends and automation is not in the file (chapter 14).
- **An FCPXML, OpenTimelineIO or EDL file does not find its media.** The paths in the file are paths on the PotionUI server. Copy the media to your editing computer and relink them in your software (chapter 14).
- **"This export no longer exists." or "The video is not ready yet."** when you download: the export was deleted, or it is still running. Export again, or wait for the end of the card.
- **A seam frame is refused.** "This shot has no previous shot." (the first shot cannot take one); "“Shot 1” has no finished take yet." or "The previous shot has no finished take with a file." (generate and choose a take for the previous shot first); "The image could not be extracted from the take." or "The image could not be extracted: try again." (try again, and tell your admin if it persists); "The project could not be saved: no image extracted." (the project must be saved first: see the save state in the project bar).
- **The project bar says "Not saved — retry".** The last save failed: the connection dropped, or the server refused the project. A message tells which. Click the save state or the **Retry** button of the message to try again. Your changes stay in the page and the next change tries again too. Until a save works, opening another project or restoring a version asks you to confirm before it drops those changes. If the message says that the content was refused or that the project is too large, ask your admin: reloading the page would lose the changes that are not saved.
- **"Project reloaded: it changed elsewhere".** The project was saved from another tab, window or device after you opened it, so the page loaded the saved version. The changes you had not saved in this page are lost. Work on a project in one place at a time; **File › Version history…** brings back an earlier state.
- **"This project was deleted elsewhere".** The project was deleted from another tab or device while it was open here. The page opened your most recently modified project, or created the starter project. The changes you had not saved are lost.
- **A media does not show or play.** The viewer says **Media offline** ("The source file of “…” is no longer available: import it again or choose a take.") and so does the thumbnail of the shot on the timeline: the file is no longer available in your PotionUI library or gallery. Import it again, or choose a take for the shot. A take whose generation you deleted from the gallery no longer plays either.
- **"1 file could not be imported" (or "N files could not be imported").** The file is no longer available in the library or the gallery, or its kind is not accepted by the window: images and videos for **Import files…** and **From the PotionUI gallery**, audio for **Import audio file…**.
- **The 3D view says that the browser cannot display 3D.** The page needs WebGL 2. Turn on the hardware acceleration of your browser, or use a recent Chrome, Edge, Firefox or Safari.
- **A scene from an image failed.** The list and the view give the reason: your GPU minutes are used up, the Image to Splat preset is not available to you (ask your admin), or the image could not be read or extracted from the video. Click **Try again**; if it fails again, tell your admin.
- **Holes appear when the camera moves.** A picture only shows one side of things: beyond about 15° or 25 % from the source view, empty patches appear. Stay closer to the **Source view**, lower the amplitude, or build another scene from a picture taken from the angle you need.
- **The reference video renders slowly.** Your computer's graphics card draws each frame, and a hidden tab or a minimized window slows it down a lot. Keep the page visible until the end; **Cancel** stops it.
- **A Blender file does not load.** Export a `.glb` (glTF binary) from Blender, or a `.gltf` with its data embedded: a `.gltf` with separate `.bin` or texture files cannot be read.
- **The assistant does not answer, shows no card or acts on the wrong project.** See chapter 10, "If it does not work".


## 19. Glossary

| English | Français | Meaning |
|---|---|---|
| shot | plan | A clip of the film, one generation. |
| take | prise | One generated version of a shot: a real video made by the engine you picked. |
| draft | brouillon | A fast, lower-resolution take to judge motion and framing. |
| final | final | The chosen take, enlarged (upscale) or generated again at the largest resolution (re-render). |
| engine | moteur | What makes the takes: a video preset on your admin's hardware, or a cloud model. |
| variant | variante | One of the takes (A, B, …) made for the same shot in one generation. |
| seed | graine | The number that fixes the randomness of a take; the same seed gives a similar take. |
| calibration | calibration | The real durations of your past generations, kept per preset, engine and resolution, that the estimate uses for its time; it shows "—" until there is one. |
| match | raccord | Making two neighbor shots look alike (color) or keep the same identity. |
| seam frame | image de raccord | An image taken from a take and set as the first or last frame of a shot, usually the last image of the previous shot, so that a shot starts where the previous one ended (chapter 12). |
| fade | fondu | A gradual start or end of a clip. |
| playhead | tête de lecture | The current position on the timeline. |
| range | plage | A part of the timeline between an in point and an out point. |
| global direction | direction globale | The text that guides every generation. |
| prompt language | langue des prompts | The language of the global direction and of the shot prompts of a project, English or French. |
| version | version | A saved state of the project; **Version history…** lists them and restores one. |
| shot prompt | instruction locale | The text for one shot; it completes the global direction. |
| Control video | Control video | A guide video that sets the motion. |
| Gaussian Splat | Gaussian Splat | A 3D scene made of many small colored blobs, built from a picture or imported, that a camera can move through (chapter 4). |
| 3D shot | plan 3D | A camera path in a 3D scene, on the 3D shot row of the timeline. |
| source view | vue d’origine | The camera of the picture a scene was built from: the scene looks right around it. |
| reference video | vidéo de référence | The video of a 3D shot rendered frame by frame, which guides the camera of a generation. |
| H3 profile | profil H3 | FL2VA, Ref2VA or Hybrid AV: what guides the generation. |
| mode | mode | A way the PotionUI chat works, with its own instructions and tools. This page uses **Video Producer assistant**; a conversation keeps its mode. |
| tool | outil | An action the assistant can run in your project: write a shot prompt, fix conflicts, split the synopsis, check continuity. |
| approval | approbation | The card where you accept (**Approve**) or refuse (**Reject**) what the assistant proposes. Nothing changes before you approve. |
| context | contexte | The summary of your project that the page sends to the assistant with each message (chapter 10). |
| export job | job d'export | A video export waiting or running on the server, with its state and its progress. Once it ends it stays in **Previous exports** (chapter 14). |
| mezzanine | mezzanine | The high-quality intermediate video that the server assembles first and then converts into the MP4 you download. You never handle it (chapter 14). |
