# Video Producer: user guide

Français : [Video Producer : guide utilisateur](/docs?doc=plugin/video-producer/user-guide.fr) (fichier `docs/user-guide.fr.md`).

This guide explains how to make a short film with Video Producer. Interface labels are written in **bold**. Video Producer is delivered in steps. This version has the complete interface, in English and in French, saves your projects, imports your media and generates real takes and finals (chapters 8 and 9), but some functions are still simulated (chapter 17). A chapter about something that does not exist yet ends with "Available from step N". The administrator guide is a separate page that only admins see.

## 1. What Video Producer is

Video Producer is a PotionUI plugin for audiovisual editing, AI sequence generation, art direction, sound creation and 3D scene preparation, all in one page. You write a synopsis, split it into shots, generate quick draft takes, choose the best one, turn it into a final, then cut, match colors, mix sound and deliver. It opens from the **Video Producer** entry in the sidebar.

Before you start:

- An admin has to prepare at least one engine (this machine, a studio server or a cloud model) and at least one video preset assigned to you. If the Production bar shows no engine, see chapter 18.
- Your admin also sets the draft resolution, how many generations you can have in progress at once, and may limit the GPU minutes you can use per month.
- Generation is real: the takes are videos made by your admin's machines or cloud account, and they take time. The estimate in the Production bar tells you what to expect before you start (chapter 8).
- The model MiniMax H3 (the **MiniMax H3** entries of the engine pop-up) comes with a license that excludes use, and anything generated with it, in the European Union, the United Kingdom, the United States and South Korea without an individual authorization from MiniMax, and that asks a commercial product to display "MiniMax H3" prominently. Ask your admin before you use it. Video Producer does not check any of this for you.

The interface is in English by default and also exists in French (chapter 15).

The first time you open the page, it creates a starter project, "Dawn at the harbour" ("Aube sur le port" in French), and opens it. It holds a synopsis, the global direction in five fields, five shots of 5 seconds still to generate, each with its shot prompt (the sleeping harbour, the fisherman's hands, the departure, the gulls, out to sea), a title, a marker named "Cast off" and four empty audio tracks. It has no media, no take, no reference and no 3D scene. Its name, synopsis, shot names, title and marker are written in the language of the interface; its global direction and shot prompts are written in the prompt language of the project, English by default (chapter 15). Try the whole path on it, or start an empty project with **File › New project…**. On your next visits the page opens the project you used last (chapter 5).

## 2. The path in eight steps

**Help › Getting started** shows the same path as a list you can click. The eight steps:

1. **Create a project.** **File › New project…** (or **File › Open…** for an existing one). In **Project properties…** you set the name, the aspect ratio (16:9, 2.39:1, 9:16, 1:1 or 4:5), the resolution (720p, 1080p or 4K) and the frame rate (24, 25 or 30 fps). Result: an empty project that is saved as you work.
2. **Set the global direction.** In the **Director IA** workspace, tab **Direction**: world and intent, characters and identity, photography, palette and lighting, pacing and continuity. Result: a text that guides every generation.
3. **Add the references.** In **Director IA**, tab **References**: identities, 3D sets and motion guides. Result: what must stay the same from one shot to the next.
4. **Split the film into shots.** In the **Storyboard** workspace: write the synopsis, click **Propose a breakdown**, keep the shots you want and adjust their shot prompts. Result: a row of shot cards.
5. **Generate drafts.** In the Production bar, pick the **Generation engine**, quality **Draft**, then **Generate selection** (Ctrl+G). The estimate shows time, memory and quota. Result: real draft takes A, B, and so on, made by the engine you picked.
6. **Pick and make final.** In the Inspector, tab **Takes**: compare the takes, click **Choose** on the one the shot should play, then click **Make final** on the best draft take. Result: the shot moves from Draft to Final.
7. **Edit, match and mix.** Fades on the clips, color match in the Inspector tab **Color**, the console in **Mix**. Result: a finished sequence.
8. **Prepare delivery.** **File › Export video…**, **Export to other software…** or **Export subtitles…**. Result: files you can download.

The interface of all eight steps is in place, and your projects are saved as you work (chapter 5). The page opens the project you used last, or the starter project the first time (chapter 1). **New project…** starts an empty project, "Untitled project", and adds it to your projects. Drafts and finals are real since step 4. From step 6: delivery as video files.

## 3. The screen

The page has five levels of controls, from the widest to the most local, around a left panel, a center area, the Inspector and the timeline:

- **Menu bar.** Ten menus, in this order: **Video Producer**, **File**, **Edit**, **Cut**, **Shot**, **Production**, **Audio**, **View**, **Window**, **Help**. The **Video Producer** menu holds **About Video Producer**, **Preferences…**, **Keyboard shortcuts** and **Search commands…**. A menu shows "…" only when the command opens a window that asks for something, and a check mark in front of a state that is on.
- **Project bar.** On the left, the button that shows or hides the side panel, the project name (click it to rename the project) and its save state ("Saving…", "Saved at" and the time, "Modified · click to save" or "Not saved — retry"; chapter 5). In the middle, the workspace selector: **Media**, **Director IA**, **Storyboard**, **3D scene**, **Mix**. On the right, **Import**, **Export**, **Assistant**, a search button for the commands and the button that shows or hides the Inspector.
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

The timeline has a toolbar and one row per kind of item. The toolbar holds **Undo** and **Redo**, the **Select tool**, **Range tool** and **Blade tool**, **Split at the playhead**, **Duplicate**, **Delete**, the **Add** menu (**Prompt**, **Reference frame**, **Control video**, **Title**, **Marker**, **Audio track**), **Snapping**, the zoom and **Fit**. The rows are **Titles**, **Prompts**, **Frames**, **Control video**, **3D shot**, **V1 · Video** and one row per audio track, with **M** (mute) and **S** (solo). Click the ruler to move the playhead; with the Range tool, or by dragging with Alt held, draw a range. Drag a shot to change its order, drag its edges to trim it (the shots after it follow), drag the white handles at the top of a clip to set its fades, drag an audio clip to another track. Ctrl and the mouse wheel zoom. Double-click an empty spot of the Prompts, Frames or Control video row to create an item there.

## 4. Workspaces

Each workspace changes the left panel and the center. The Inspector on the right follows your selection in all of them. **Window › Timeline index** lists the prompts, frames, markers and Control videos with their time, and **Window › Background tasks** shows the generation in progress and the queue.

### Media

The media of the project in one panel. A new project has none: the panel says "No media in this project." and offers **Import media**, like the import button of its header and **Import** in the project bar; chapter 6 explains how to bring in your images, videos and audio files. Filter with the collection pills (**All**, **Images**, **Videos**, **Audio**, **Generated**), search by name without worrying about accents, double-click to preview, drag to the timeline. For a selected item the panel shows its duration, format, collection and origin, and the buttons **Preview**, **Add to cut** and, for images and videos, **Use as frame at the playhead**. The center is the viewer.

### Director IA

The left panel has three tabs. A dot on **Direction** warns that there are points to check, and **Results** shows the number of takes.

- **Direction.** Shows what guides the generation for the current range: the global direction, the shot prompt, the references and Control videos, with **View the generation summary**. Below, **To check**, the list of direction conflicts and color matches to fix, the **Project H3 profile** (FL2VA, Ref2VA or Hybrid AV, chapters 8 and 11) and the **Global direction** itself, in five fields (world and intent, characters and identity, photography, palette and lighting, pacing and continuity), with a counter out of 4000 characters. Each field has a **Library & assistant** link. The gear button, **H3 settings**, opens the **Advanced workshop**.
- **References.** Three families, **Images and identity**, **3D sets** and **Motion guides**. A reference is global (it goes with every generation) or applies to a range only; **Attach to range** sets the second. **Reference** adds one. The center shows the board of references, in two groups, **Global direction** and **On the timeline**, with a search field. Drag a thumbnail onto the Frames track to anchor it to a precise moment. A new project has no reference: the board says so, and **Reference** adds the first one.
- **Results.** The take cards of each shot (chapter 9), the **Generation queue** and **Assemble chosen takes**.

### Storyboard

On the left: the **Synopsis** (one sentence becomes one shot) and **Propose a breakdown**. The **Proposed breakdown** lists the shots: tick the ones to keep, rename them and click **Add N shots at the end**. In this version the breakdown is simulated: it only cuts the synopsis into sentences. Then **To produce**, with **Drafts left** and **Move to final** (the number of shots and the footage still to do for each), and **Continuity**, which lists the color matches to check, each with **Match color**.

In the center: one card per shot, in order, with its number, its duration, its name, its stage (**Source**, **To generate**, **Draft** or **Final**), its number of takes and its shot prompt; click the prompt to write it. Drag a card to move it. The buttons of a card appear when you hover it or select it: the main one follows the stage, **Generate**, **Make final**, **See takes** or **Regenerate**, and three icons show the shot in the viewer, insert a shot after it and delete it. While a take of the shot is in progress, the card shows its step and progress and the button is disabled. The header counts the shots per stage, adds one with **Shot** and sets the size of the thumbnails; a **New shot** tile at the end does the same. In this workspace, the Left and Right arrow keys move the selection to the previous or next shot.

### 3D scene

A new project has no 3D scene. In the left panel the **Scenes** list is empty: **Sample scene** creates a procedural point cloud, marked **Simulated**, and **Reference a Gaussian Splat file…** asks for the path of a file and adds it as a scene. Then come the **3D shots on the timeline** (**New 3D shot at the playhead**), the **Preset trajectories** (**Orbit**, **Dolly in**, **Rise**), the camera and its keyframes in the Inspector, and the **Outputs for generation**: **Capture a frame** and **Generate the Control video**. The center is the 3D view (before any scene it says "No 3D scene" and offers **Sample scene**): drag to orbit, scroll to change the distance, play to preview the trajectory. This workspace is partly simulated: see chapter 17.

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

**File › Version history…** opens the window **Version history** ("Each save creates a version"). It lists the versions of the open project, the newest first. Each row shows the number ("Version 7"), the date and time, seconds included, and the number of shots. A capture of this window, in the dark and light themes of the English interface, is in `docs/screenshots/version-history.png`. A version made by a restore adds "Restored from version N". The version you are working on carries the badge **Current** and cannot be selected.

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

What is still simulated: the takes made by earlier versions of a project, which show a procedural thumbnail marked Simulated, and the sounds of the Sound design workshop, which your browser synthesizes (chapter 17). The takes of the real generation are ordinary videos and play like any other video (chapter 9).

## 7. Inspector

The Inspector follows the selection and its title tells what is selected: **Video shot**, **Audio clip**, **Title**, **Shot prompt**, **Reference frame**, **Control video**, **3D shot**, **Marker**, **Reference** or **Console strip**. For a shot it starts with a thumbnail, the name (click it to rename the shot), the stage and the times, and has three tabs:

- **Shot.** A shortcut to the next action (**Generate drafts**, or **Make take A final**) with the engine it will use ("On" followed by the engine), **Duration and source** (the duration, where the shot starts in its source and the length of the source), **Fades** (**In** and **Out**), the **Flag** (**None**, **Favorite** or **Rejected**) and three icons to split the shot in the middle, duplicate it and delete it.
- **Takes.** The take cards of the shot, as **Final** and **Drafts**, and a button that makes more drafts (for example "2 more drafts"; chapter 9).
- **Color.** The luminance scope, the match with the previous shot, presets and fine settings (chapter 12).

The other items have their own panel:

- **Audio clip:** its track, start, duration, gain, fades, and a button that opens its strip in the console.
- **Title:** the text, the subtitle, the start and the duration.
- **Shot prompt:** the text, the **Library & assistant** link, the **Editor** button, the warnings about the direction, the start, the duration, the influence, and the global direction that applies.
- **Reference frame:** the image (picked among the images of the project, which a new project does not have), the position, the role (start, end, transition, identity, style, 3D capture) and the strength of its influence.
- **Control video:** the name, its source (**3D scene** or **Imported video**), the start, the duration and the strength of its guidance. In its range the motion comes from the guide: camera instructions in the prompts are ignored.
- **3D shot:** the scene, the start, the duration and the **Camera**.
- **Marker:** the label and the position.
- **Reference:** the name, the role, the scope (**Global direction** or **Specific moment**) and the shot it applies to.
- **Console strip:** the name, the role, the effects (**Equalizer**, **Compressor**, **Filter**) and the sends.

In the **3D scene** workspace, with a 3D shot selected or nothing selected, the Inspector shows the **Camera**: focal length, pan, tilt, distance and target height, **Keyframe**, **Follow the path** and the list of keyframes. With nothing selected in the other workspaces, it shows the project (format, H3 profile, content), a reminder of the main shortcuts and a **Project properties…** button.

## 8. Production bar and generation

The Production bar reads like a sentence: a target (**Shot**, **Range** or **Sequence**), the range with the number of shots and prompts it holds, a quality (**Draft** or **Final**), an output mode, the **Generation engine**, the **Advanced workshop**, then the estimate, **Add to queue** and **Generate selection**. A number with a warning icon after the counters is the number of direction conflicts in the range; click it to see them. Generation is real: a take is a video made in the background by the engine you pick.

### Choose the engine

- The output mode **AI generation** is the real one. **3D render** and **3D render + AI** are still simulated (chapter 17); with **3D render** the main button reads **Prepare the render**.
- The **Generation engine** pop-up lists what your admin enabled and assigned to you, in groups named after the backends. A group named after your admin's own backend holds the video presets that run on their hardware, for example **Wan 2.1 / 2.2** or **MiniMax H3**. Each cloud provider has its own group, with its video models by name. Your choice is saved with the project. Whether a preset runs on this machine or on a studio server is decided by PotionUI, and the take card tells you afterwards. Hover the pop-up to see the group and, for a preset that runs on the admin's hardware, the free memory of its GPU ("16.0 / 24.0 GB free"). On a window narrower than 1400 pixels the pop-up is hidden: use **Production › Generation engine…**, which opens the **Advanced workshop** on its engine step. A capture of the pop-up and of the bar around it, in the dark and light themes of the English interface, is in `docs/screenshots/engine-popup.png`.
- With no engine, the pop-up reads "No engine" and the bar says "No generation engine: an administrator must enable a video preset or a cloud model." An admin also sees the link "Open plugin settings". When the engine of a project is no longer available, the pop-up reads "Engine no longer available" and the bar says "The engine of this project is no longer available: pick another one." A project from an earlier version that named a placeholder engine is moved to the matching real engine when you open it.
- **Quality.** **Draft** makes quick takes at the resolution your admin chose, or the closest the engine offers; hover it to see which ("Quick draft in 832×480: check motion and framing"). **Final** makes takes at the largest resolution of the engine ("Final quality in 1280×720: keep it for the chosen takes"). To improve a draft you like, **Make final** (chapter 9) is usually the better way: it keeps the picture you chose.
- The **Advanced workshop** has three steps: **Sources and guides**, **Engine and Hybrid builder** and **Sound and delivery**. It opens from the bar, from **Production › Advanced workshop…** and, for the engine, from **H3 settings** in Director IA. Its **Variants per window** field (1 to 4) sets how many takes, A, B and so on, each shot gets when you generate. The settings that the engine does not use are greyed there and carry the badge "Not sent with this engine" (chapter 17).

### Read the estimate

The estimate sits on the right of the bar once an engine is picked: a short line with the time, the memory (a cloud model has none) and, on a wide window, the minutes of quota or, for admins, the cost. Hover it for the detail. It follows your changes half a second after you stop, once the project is saved: until then it reads "The estimate updates once the project is saved." and, while it computes, "Estimating…". The detail has these lines:

- **Scope.** The shots and variants and the resolution: "2 shots × 2 variants in 832×480".
- **Time.** "Time ≈ 4 min on MiniMax H3 (measured on 3 takes)". It comes from the takes already made with the same preset, engine and resolution, whose real durations were measured: that is the calibration. With none yet it reads "Time: — (no measure yet on MiniMax H3)" and the bar shows "—". It fills in after a few generations.
- **Memory.** "Memory ≈ 22.5 GB, 16.0 GB free on Local Generation". It is an estimate from the size of the model files, never a guarantee. "Memory: unknown" when it could not be estimated.
- **Quota.** Your monthly Video Producer GPU minutes: "Quota: 5 min needed, 40 of 60 min left this month", "Quota: exempt" if you are exempt, and "Cloud: no GPU quota used" for a cloud model, which does not use them. It shows as **GPU quota** in the status bar when your admin set a limit. When your minutes are limited, the minutes of a take are reserved when it is created and adjusted to its real duration when it ends; a take that fails or is cancelled gives them back. With no limit, or if you are exempt, no minute is reserved or adjusted. Until a preset has been measured, each second of video counts for 10 seconds of GPU.
- **Cost.** Admins only, for a cloud model: "Cost ≈ $0.84", or "Cost: unknown for this model" when the provider publishes no price.

### Blocks and warnings

What blocks **Generate selection** (the button is disabled and the bar shows the first reason; hover it to see them all):

- no valid range;
- neither a global direction nor a shot prompt in the range;
- an empty shot prompt in the range;
- a 3D output mode with no 3D shot in the range;
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
- the FL2VA profile with no frame linked to a shot: "“Shot 2” has no linked frame: it will be generated from text only." The generation goes on from the text, and the card of the take says "text only";
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

| Profile | Wan 2.1 / 2.2, LTX-2 / 2.3, LTX-2.5, cloud models | MiniMax H3 | MiniMax H3 Fast and VDN |
|---|---|---|---|
| FL2VA | Yes | Yes | Yes |
| Ref2VA | Greyed | Yes | Greyed |
| Hybrid AV | Greyed | Yes | Yes |

- A greyed profile carries a badge such as "Ref2VA · Hybrid AV: MiniMax H3 only", with the explanation "Wan 2.1 / 2.2 cannot generate Ref2VA, Hybrid AV: reference images (Ref2VA) and generated sound (Hybrid AV) need MiniMax H3." In the **References** tab, "Not sent with this engine" tells you that the engine ignores the references ("References are sent only with the Ref2VA profile on MiniMax H3; Wan 2.1 / 2.2 ignores them.").
- **FL2VA** uses the frames linked to the shot: a start and an end frame give a take "first and last frames", a start frame alone "first frame", and no frame "text only", with the warning above.
- **Ref2VA** sends the references of the shot, then the global ones, to MiniMax H3: up to 9 images, 3 videos and 3 audio files.
- **Hybrid AV** works like FL2VA on MiniMax H3, whose model makes the picture and the sound together. The track that drives the performance (Advanced workshop) is not sent yet (chapter 17).

## 9. Takes and final

A take is one generated video for one shot. Its video is an ordinary PotionUI generation: it stays in your generation history (the gallery), even if you delete the take here.

- Drafts are made at the resolution your admin chose (832×480 unless changed) or the closest the engine offers. The frame rate of a take is set by the preset (Wan 16 fps, MiniMax H3 24 fps). The timeline and the exports use the frame rate of the project.
- Several variants are made per shot: A, B, and so on. A new generation for the same shot goes on with the next free letters (C, D…), separately for drafts and finals; **Retry** and **Make final** keep the letter of the take they come from. They are listed in the Inspector, tab **Takes** (as **Final** and **Drafts**), and in Director IA, tab **Results**, grouped by shot.

### The take card

- The thumbnail carries the letter of the take. Click it to preview the take in the viewer ("Preview take A"); **Back to the sequence** brings you back.
- The first line says "Draft", "Final" or "Final · upscale", then the state ("Queued", "Generating", "Failed", "Cancelled") or, once finished, the duration. The next lines give the profile and how the shot started ("FL2VA · first and last frames", "FL2VA · text only", "FL2VA · first frame", "Ref2VA · references"), the resolution and, for a final, the take it comes from ("from A"), the seed ("Seed 123456") and the engine that made it (the preset or the model, then the backend).
- A queued take shows only its state ("Queued") above an empty line; a take that is generating shows the step, the percentage and a progress bar. When it fails, it shows the reason that PotionUI gives (in English) or, when it gives none, "The generation failed (cuda_oom)." with the code.
- **Compare** puts the take beside a second one in the viewer, both playing in a loop ("Pick a second take to compare"). **Keep** (the star) and **Reject** (the thumb down) flag the take; click again to remove the flag. The export warns about a shot whose take is flagged Reject. **Generation details** opens PotionUI's window about the generation. **Delete** asks "Delete this take?" ("Take A of “Shot 2” leaves the list. The video stays in your generation history.").
- A capture of take cards, in the dark and light themes of the English interface, is in `docs/screenshots/takes-cards.png`.
- On a take in progress, **Cancel** stops it. On a failed one, **Retry** starts a new take.

### Choose a take

**Choose** puts the take on the shot: it plays on the timeline, the shot becomes Draft or Final, and the card shows a check mark and **Used**. Only one take is chosen per shot. The first draft that finishes for a shot that was still "To generate" is put there for you, and so is a finished final. In the viewer, a take previewed outside the cut has **Use this take**. **Assemble chosen takes** (Results tab) puts all the chosen takes in the cut; without any it says "First choose takes for the shots."

### Make final

**Make final** on a draft card (also the button of a Storyboard card, **Make take A final** in the Inspector, **Shot › Make take final** and Ctrl+Shift+G) opens the window "Make final · Shot 2 · A" with the line "Draft in 832×480 · seed 123456". It offers two ways:

- **Upscale** is the default. The engine enlarges the take as it is: the picture and the motion do not change, and it is the fastest way. Wan, LTX, MiniMax H3 Fast and VDN, and cloud takes go through SeedVR2 ("SeedVR2 enlarges this take as it is: fastest, the motion does not change."); a take of the base MiniMax H3 preset uses the upscale mode of its own preset ("MiniMax H3 enlarges this take with its own upscale mode: the motion does not change."). Pick the **Target resolution**: 720p, 1080p, 1440p or 4K (the window starts on the resolution of your project), then click "Upscale to 1080p".
- **Re-render at full resolution** generates the shot again at the largest resolution of the engine, with the same seed: "slower, the result may differ slightly."

When no upscaler is assigned to you, the window shows "Upscaler not available" ("No upscaler is assigned to you: ask an administrator to enable SeedVR2, or render again at full resolution."), the resolutions are greyed and only the re-render is offered. A take of the base MiniMax H3 preset does not need SeedVR2, as long as its preset is assigned to you. A capture of this window, in the dark and light themes of the English interface, is in `docs/screenshots/make-final.png`.

The new take is a **Final** one ("Final" or "Final · upscale") that says which draft it comes from ("from A"). You get "Upscale to 1080p started" or "Render at 1280×720 started", the final appears on the card list when it ends, and it is put on the shot ("Final version ready and applied to the shot"). A final uses GPU minutes like any take and is checked against your quota.

## 10. Assistant

The **Assistant** button, **Window › PotionUI assistant** and Ctrl+J open the PotionUI chat, in the **Video Producer** mode. The assistant can:

- write the prompt of the selected shot;
- fix the contradictions between the global direction and the shot prompts;
- split your synopsis into shots;
- check the continuity between shots.

Every change to the project asks for your approval before it is applied. The assistant knows the workspace you are in, your selection, the playhead, the range, the global direction, the synopsis and the state of the production. It needs your admin to have set up a language model.

In this version the button, the menu and the shortcut already open the PotionUI chat, and so do the links **Ask the PotionUI assistant** (prompt library) and **Ask the assistant** (sound design workshop). The four actions above arrive with step 5.

Available from step 5.

## 11. Prompts: library and composer

The window **Prompt library & assistant** opens from **Window › Prompt library**, or from the **Library & assistant** links placed near a text (in the fields of the global direction, in the Inspector for a shot prompt and in the window that edits a shot prompt). It writes into a target, shown under its title: one of the five fields of the global direction, or a shot prompt. Opened from the menu it has no target and copies the prompt to the clipboard (**Copy the prompt**). The window has two tabs, **Library** and **Composer**, and a link, **Ask the PotionUI assistant**, that closes the window and opens the PotionUI chat. The names, descriptions and categories of the templates and the choices of the composer exist in English and in French and follow the language of the interface; the texts they insert follow the prompt language of the project (chapter 15).

- **Library.** Five libraries, **Built-in**, **Personal**, **Project**, **Favorites** and **History**, and nine categories (Cinema, Camera, Lighting, Film styles, Dialogue, Photography, Sound, Continuity, To avoid). Search by name, description or keyword; the star marks a favorite. Each template says which H3 profiles it suits. A template can have variables, such as the subject or the place, that you fill in before inserting it. The **Editable preview** can also be edited by hand. **Save to Personal** keeps your version, and every inserted text goes to **History**. A new project starts with the built-in templates and one personal template; **Project**, **Favorites** and **History** are empty until you star a template or insert a text.
- **Composer.** Builds a prompt from four parts, **Camera movement**, **Lighting**, **Film style** and **Dialogue or acting intent**, for the H3 profile you pick (it starts from the profile of the project). Choose one option per part, or type your own in **Other…**, and fill in the subject, the action, the place and the emotion. The **Final prompt** stays editable, and **Recompose from the choices** brings it back. **Required references** tells whether the range has what the profile needs. When a Control video covers the range, the camera part is **Set by the Control video** and locked.
- **Insert** writes the text into the target: **Add to the text** adds it to the existing text, **Replace** replaces it.

The three H3 profiles and what each one asks for on the range:

| Profile | Meaning | It asks for | Engines |
|---|---|---|---|
| FL2VA | Continuity between the start and end images. | Start and end frames in the range. Without any frame, the shots are generated from text only. | All of them. |
| Ref2VA | Keep the identity of the references during the action. | An identity reference (character, object). The generation follows your references. | MiniMax H3 only (not its Fast and VDN variants). |
| Hybrid AV | The soundtrack, rhythm and dialogue drive the picture. | An existing audio track in the range (dialogue or music). | MiniMax H3, Fast and VDN. |

The engine, not the table, has the last word: the page greys a profile the chosen engine cannot generate (chapter 8). The audio tracks of the project are not sent to the engine yet: MiniMax H3 makes the sound itself, and the track that drives the performance stays simulated (chapter 17).

When a Control video is present, the motion comes from the guide.

## 12. Color and continuity

An alert appears only when two neighbor shots do not match: "“Shot” is brighter, darker, warmer or cooler than the previous shot". It shows in Director IA (tab **Direction**, under **To check**), in the Storyboard (under **Continuity**, and as a warning icon on the card of the shot) and in the Inspector. **Match** fixes it in one click by adjusting exposure and temperature to the previous shot. The measure is made on the real thumbnails of the takes. The **Color** tab also has the luminance scope, six presets (Original, Golden light, Cold morning, 35 mm film, Blue night, Soft) and fine settings (**Exposure**, **Contrast**, **Saturation**, **Temperature**), with **Reset** and **To all shots**. Before a shot has an image, the tab says that color can be adjusted once the shot is generated.

In this version the measure is already made, on the image of each shot that has one. The starter project has none yet, and the Storyboard then says "No match to check yet: the shots have no image." A similarity percentage between two generated shots can also appear in the alerts ("Check the identity between … and … (similarity 78 %)"): it is simulated (chapter 17). Color is real.

Available from step 6.

## 13. Audio and subtitles

Audio lives in tracks, each with a role: Dialogue, Music, Ambience or SFX. **Audio › Add audio track** and **Audio › Import audio file…** bring sounds in; **Audio › Mixing console** shows the console. In the console each strip has a role, effects (**Equalizer**, **Compressor**, **Filter**; **+ effect** adds one), sends to the reverb and delay buses (R and D), pan, a fader (double-click it to go back to 0 dB), a meter, **M** and **S** and an automation button; the auxiliary buses and the **Master** follow. The pills at the top show one role only. **Voice and dialogue…** and the sound design commands (**Ambience…**, **Foley…**, **Texture…**, **Impact…**, **Musical intent…**) open the **Sound design workshop**, which is simulated (chapter 17). The text of a dialogue is real: it feeds the subtitles, together with the titles of the timeline.

The four tracks of a new project are empty. **Audio › Import audio file…** brings in your own audio files (chapter 6). The console plays them for real: the faders, mute and solo, pan, equalizer, compressor, filter and sends act on the sound you hear, the meters show it, and the clips of the timeline draw the waveform of the file. The sounds that the Sound design workshop prepares are still synthesized by your browser (WebAudio).

## 14. Exports

**File › Export video…** opens **Export and share**, with three tabs:

- **Video.** Pick a format, a resolution and the extent (**Whole sequence** or **Range**), and say whether to add the audio stems. The formats are **Master file · ProRes 422**, **Web · H.264 MP4**, **Social media · vertical H.264** and **Archive · H.265**. The real export writes H.264 MP4 or VP9 WebM; ProRes 422, H.265 and the audio stems stay simulated and carry the badge.
- **To other software.** Final Cut Pro (`.fcpxml`), OpenTimelineIO (`.otio`) and EDL CMX 3600 (`.edl`). They are real files.
- **Subtitles.** An SRT file built from the dialogue text and the titles. **File › Export subtitles…** opens this tab.

Before the export, the window warns about shots that are not final yet, shots that use a take you flagged **Reject** and direction conflicts that are not solved. Exports are written to your PotionUI storage, in a `video_producer/exports/` folder, and you download them from the page. Your admin sets a size budget for that folder per user.

In this version only the last two tabs produce files. Their button (the word "Download" followed by the file name, which comes from the project name) builds the file in your browser and saves it through the browser: nothing is written to your PotionUI storage. The media paths inside the Final Cut Pro, OpenTimelineIO and EDL files are made from the names of the media, not paths of real video files, and a shot without media becomes a gap. The **Video** tab shows a progress bar and ends with a note saying that no video file is written at this stage.

Available from step 6.

## 15. Language

Video Producer exists in English and in French. Choose **English** or **Français** in **Video Producer › Preferences…**, setting **Language**, or click the `EN` or `FR` reminder at the left of the status bar, which opens the same window. The change is immediate and is saved for you alone, on the server; if the saving fails, a message says that the language changed for this session only. Until you choose, the page follows the language of your browser (French if it is French, English otherwise).

The **Preferences** window has five other settings: **Prompt language** (see below), **Preview quality** (**Best performance**, **Balanced** or **Best quality**, without effect yet), **Snapping by default**, **Framing guides** and **Single-key shortcuts** (chapter 16). Except **Prompt language**, which is saved with the project, they apply to the current session and are not saved.

What is translated: the menus, the windows, the buttons, the tooltips, the messages, the names given to new items (for example a new shot or a new track), the prompt library with its templates, categories and composer choices, and the way numbers and durations are written. What is never translated is the content of your project: your own texts (the synopsis, the global direction, the shot prompts, the names and titles you typed, the project name) and the starter project, which is created once and is not translated afterwards. Product terms such as Director IA, Storyboard, Control video or FL2VA are the same in both languages.

### Prompt language

Each project has its own **Prompt language**, English or French. It is the language of the texts that are sent to the models, the global direction and the shot prompts, and it does not depend on the language of the interface. It is English by default.

Change it in **Project properties…** (the setting says "Language of the direction and prompts sent to the models. Changing it does not rewrite existing text.") or in **Preferences…** (the setting says "Applies to the current project"). It is saved with the project. A new project always starts in English, whatever the language of the interface or of the project that is open.

What it changes:

- **The starter project.** Its global direction and its shot prompts are written in English, even when the interface is in French. Its name, synopsis, shot names, title and marker follow the language of the interface.
- **The prompt library.** The text that the built-in templates insert, their placeholders (the subject, the place and so on) and the default values of those placeholders are written in the prompt language. The names, descriptions and categories of the templates follow the language of the interface.
- **The composer.** The **Final prompt** is composed in the prompt language. The choices you click keep the language of the interface.
- **The direction checks.** The checks that read your texts use the rules of the prompt language: the contradictions between the global direction and a shot prompt (for example a direction that excludes neon and a prompt that asks for it), and the camera instructions in a prompt that a Control video covers. A text written in the other language is not checked.
- **The assistant.** Available from step 5: it writes shot prompts in the prompt language.

What it never changes: nothing you typed is translated, and changing the setting rewrites no existing text. Set the language before you write, or rewrite the texts yourself.

## 16. Keyboard shortcuts

The table gives the shortcuts for Windows and Linux. On a Mac, read ⌘ for Ctrl, ⌥ for Alt and ⇧ for Shift; the menus and the tooltips show the notation of your system, and the side panel is ⌃⌘1 (Control and Command). **Search commands…** (Ctrl+K) finds any command, and **Keyboard shortcuts** (Ctrl+Alt+K) lists those that have a shortcut.

| Shortcut | Action |
|---|---|
| Ctrl+K | Search commands… |
| Ctrl+Alt+K | Keyboard shortcuts |
| Ctrl+, | Preferences… |
| Esc | Close, in this order: the command search, the open window, the open menu, a take preview or comparison; otherwise clear the selection |
| Ctrl+Z, Ctrl+Shift+Z | Undo, Redo |
| Ctrl+S | Save |
| Ctrl+O | Open… |
| Ctrl+I | Import files… |
| Ctrl+Alt+J | Project properties… |
| Ctrl+E, Ctrl+Shift+E | Export video…, Export to other software… |
| Ctrl+G | Generate selection |
| Ctrl+Alt+G | Add selection to queue |
| Ctrl+Shift+G | Make take final |
| Ctrl+J | PotionUI assistant (opens the chat) |
| Ctrl+Alt+1 | Side panel |
| Space | Play / pause |
| Ctrl+B | Split at playhead |
| Ctrl+D | Duplicate |
| Backspace, Delete | Delete |
| A, R, B | Select tool, Range tool, Blade tool |
| I, O | Set in point, Set out point |
| M | Add marker |
| N | Snapping |
| Left arrow, Right arrow | Move the playhead by 1/25 s (1 s with Shift) |
| Left arrow, Right arrow (Storyboard) | Select the previous or next shot |
| Home | Go to the start |

The single-letter shortcuts (A, R, B, I, O, M and N) can be turned off in **Video Producer › Preferences…**, setting **Single-key shortcuts**, which is on by default. Space, Backspace, Delete, the arrows and Home do not depend on it.

When the shortcuts work:

- Only while the focus is on the page and not in a text field. With a text field focused, a window open (a PotionUI picker or confirmation included) or the command search open, the other shortcuts are off; Esc, Ctrl+K and Ctrl+Alt+K always act. While the PotionUI chat is open, the shortcuts of the page are off.
- The menus and the **Keyboard shortcuts** window also show other combinations, for example Ctrl+N, Ctrl+C, Ctrl+V, Ctrl+F or Ctrl+1 to Ctrl+5 for the workspaces. They are not active in this version: use the menu, the buttons or the workspace selector.

## 17. What is simulated

Some parts keep their interface but do not do the real thing yet. They carry a gray dashed badge, **Simulated**, never a yellow one: yellow is kept for real points to check. **Help › Simulated features** opens the list. The same gray badge also marks what the engine you picked cannot do (a greyed profile, "Not sent with this engine" on the references and on the workshop settings, "Upscaler not available"; chapters 8 and 9).

The badge **Simulated** appears in the header of the windows **Reference a Gaussian Splat file** and **Sound design workshop** (titled **Voice and dialogue** for a voice); next to the formats **Master file · ProRes 422** and **Archive · H.265**, next to the audio stems and in the footer of the **Video** tab of the export window; on the automation button of the console strips; on the **Sample scene** and on the preview of a Gaussian Splat file in the 3D scene; and on a take made by an earlier version of the project, on its card ("Simulated take from an earlier version of the project: read only.") and in the viewer ("Final take · simulated AI", "720p draft · simulated AI"). The takes of the real generation never carry it. A few notifications are flagged the same way.

Already working in this version: the generation itself (the engines your admin enabled, the estimate, the takes with their progress, cancel and retry, the finals by upscale or re-render, the quota and the notifications), saved projects, **File › Open…**, **File › Version history…** and **File › New project…**, the import of your images, videos and audio files with their thumbnails and their playback, editing on the timeline (trim, fades, split, snapping, range, markers, undo and redo), the selection and the Inspector, the Storyboard, the prompt library and the composer, the direction conflict checks, the color match, the camera, the trajectories and the keyframes of the 3D scene, the mixing console playing your audio files, and the Final Cut Pro, OpenTimelineIO, EDL and SRT files, which are real files.

The window **Simulated features** lists eight items. For each one, the table says what it does in this version and what it becomes once all the steps are delivered.

| Item in the window | In this version | Once all the steps are delivered |
|---|---|---|
| **3D render modes and engine settings** | The output modes "3D render" and "3D render + AI" start nothing. The settings greyed in the Advanced workshop are not sent to the engine: the seed (each take draws its own), the final resolution (the final uses the largest resolution of the engine), steps, CFG, LoRA, windows, consistency, post-processing and the Hybrid AV audio driver; nor are the Control videos and the Hybrid builder weights. Takes made by earlier versions keep their numbered thumbnail. | Stays simulated. AI generation itself is real: see chapters 8 and 9. |
| **Synopsis breakdown** | One sentence becomes one shot. | The assistant proposes the breakdown. Available from step 5. |
| **Identity check** | The similarity between shots is simulated. The color check really analyzes the images. | Color matching is measured on the real thumbnails of the takes (from step 6). The similarity percentage stays simulated, because no identity measure is available to plugins. |
| **Video render** | No video file is written. The Final Cut, OTIO, EDL and SRT exports produce real files. | H.264 MP4 or VP9 WebM videos assembled with ffmpeg and written to your storage. ProRes 422, H.265 and audio stems stay simulated: PotionUI's video converter writes H.264 MP4 or VP9 WebM only, and no per-role audio render exists. Available from step 6. |
| **Gaussian Splat** | The referenced file is not loaded; the sample scene is a generated point cloud. | Stays simulated: the scene stays a 2D point preview and Gaussian Splat files are referenced, not loaded. |
| **Control video** | Computing the guide from the 3D scene is simulated. | Stays simulated: the guide video is not rendered from the scene, an imported Control video is not sent to an engine and the 3D capture is not rendered from the scene. The production modes **3D render** and **3D render + AI** depend on that guide and stay simulated. |
| **Voice and sound design** | Preparation is simulated; the preview is a simple synthesis. | Stays simulated: voice, character and timbre settings do not produce speech, lip sync has no separate step (MiniMax H3 makes picture and sound in one pass) and no preset prepares ambience, foley, texture, impact or music for the workshop. The text of the dialogues does feed the subtitles for real. |
| **Edit audio** | The audio files you import play for real through the console: faders, mute and solo, pan, equalizer, compressor, sends and meters work on them. The sounds prepared by the Sound design workshop are synthesized in real time (WebAudio). | Stays simulated for the workshop sounds, because no preset prepares them, and for the automation curves: the automation button only switches a mode, no curve is recorded. |

The window does not list every setting of the **Advanced workshop** that the engine does not use: consistency between windows, lock character identity, motion guide first, the generation windows with their length and overlap, the final resolution, the seed, the steps, the guidance (CFG), the LoRAs, the track that drives the performance, lip sync, follow the rhythm of the cut, audio / picture offset, result naming, post-processing and insert variant A automatically. They stay in the project, but they are not sent to the engine and drive no generation: a preset only exposes the controls it declares, and MiniMax H3, for example, has no guidance and no negative prompt. The workshop greys them and marks each one with the badge "Not sent with this engine" (hover it: "The Video Director builds the request from the shots, the direction, the frames and the references; this setting stays in the project but does not change the takes."). **Variants per window** stays active. The Hybrid builder weights and its saved profiles, and the guidance of a Control video, are not sent either, but they are not greyed. What counts is the engine, the quality, the variants and what is in your project: the direction, the shot prompts, the frames and the references. The seed of a take is drawn by the server and shown on its card, and the resolutions follow the draft and final rules of chapter 8.

The assistant, for its part, is not simulated: it is the PotionUI chat in Video Producer mode, which writes shot prompts, fixes conflicts with the global direction, splits a synopsis into shots and checks continuity, and you approve each change before it touches the project (available from step 5).

## 18. Troubleshooting

- **The Production bar shows no engine.** The pop-up reads "No engine". Your admin has not finished the setup: an engine, a video preset assigned to you, or a video model turned on for the cloud provider. Ask them to open Admin → Plugins → Video Producer.
- **The estimate shows "—" for the time.** Nothing has been measured yet for this preset, engine and resolution (the calibration is empty). It fills in after a few generations.
- **"Will stream through host RAM, slower."** The memory estimate is above what the GPU has. The generation is not blocked. If the server lacks free memory for it, the engine refuses to start and the take fails (`host_ram_oom`).
- **The quota is spent.** **Generate selection** says "GPU quota exceeded" until the next month or until your admin raises the limit of your plan. Running generations are not stopped, and a take that fails or is cancelled gives its minutes back. The first takes of a preset count 10 seconds of GPU for every second of video, which can look generous until the real durations are measured.
- **Generate selection is disabled.** Read the message in the bar: no range, no direction and no shot prompt, an empty prompt, a 3D mode with no 3D shot, no engine, a preset that is not yours, a profile the engine cannot generate, models to install, a cloud model to pick, or the quota.
- **"Models to install for this preset: …".** Your admin has not downloaded the model files that preset needs. Ask them.
- **A warning says the shots will be generated from text only.** The FL2VA profile has no frame linked to the shot. Add a start or an end frame, or pick another H3 profile; the generation is not blocked.
- **A take stays Queued.** Your admin limits how many generations you can have in progress at once: the take starts by itself when one of yours ends. If it stays Queued while nothing of yours is running, tell your admin.
- **A take failed.** The card shows the reason that PotionUI gives (in English) or, when it gives none, "The generation failed" followed by a code. **Retry** starts a new take for the same shot with the same seed. Typical causes: the GPU ran out of memory (`cuda_oom`: try a draft, a shorter shot or another engine); a model file is missing on the server (`missing_model_file`: ask your admin to download it again); the server ran out of memory while streaming the model (`host_ram_oom`). If PotionUI was restarted during the generation, the take is marked failed and cannot resume: use **Retry**.
- **"Upscaler not available" in Make final.** No upscaler is assigned to you: SeedVR2 enlarges the takes of Wan, LTX, MiniMax H3 Fast and VDN and of cloud models. Use **Re-render at full resolution**, or ask your admin about SeedVR2.
- **References are ignored with MiniMax H3.** Ask your admin to check the model file picked for the References mode. The engine ignores the references of a profile other than Ref2VA, and of any other preset.
- **I closed the page during a generation.** The takes go on; open the project again to find them. The notifications tell you when they end.
- **An export fails.** Ask your admin about ffmpeg, or free some of your exports: the folder has a size budget.
- **The project bar says "Not saved — retry".** The last save failed: the connection dropped, or the server refused the project. A message tells which. Click the save state or the **Retry** button of the message to try again. Your changes stay in the page and the next change tries again too. Until a save works, opening another project or restoring a version asks you to confirm before it drops those changes. If the message says that the content was refused or that the project is too large, ask your admin: reloading the page would lose the changes that are not saved.
- **"Project reloaded: it changed elsewhere".** The project was saved from another tab, window or device after you opened it, so the page loaded the saved version. The changes you had not saved in this page are lost. Work on a project in one place at a time; **File › Version history…** brings back an earlier state.
- **"This project was deleted elsewhere".** The project was deleted from another tab or device while it was open here. The page opened your most recently modified project, or created the starter project. The changes you had not saved are lost.
- **A media does not show or play.** Its file is no longer available in your PotionUI library or gallery. Import it again. A take whose generation you deleted from the gallery no longer plays either.
- **"1 file could not be imported" (or "N files could not be imported").** The file is no longer available in the library or the gallery, or its kind is not accepted by the window: images and videos for **Import files…** and **From the PotionUI gallery**, audio for **Import audio file…**.

Exports from step 6.

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
| fade | fondu | A gradual start or end of a clip. |
| playhead | tête de lecture | The current position on the timeline. |
| range | plage | A part of the timeline between an in point and an out point. |
| global direction | direction globale | The text that guides every generation. |
| prompt language | langue des prompts | The language of the global direction and of the shot prompts of a project, English or French. |
| version | version | A saved state of the project; **Version history…** lists them and restores one. |
| shot prompt | instruction locale | The text for one shot; it completes the global direction. |
| Control video | Control video | A guide video that sets the motion. |
| H3 profile | profil H3 | FL2VA, Ref2VA or Hybrid AV: what guides the generation. |
