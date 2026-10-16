# Video Producer: user guide

Français : [Video Producer : guide utilisateur](/docs?doc=plugin/video-producer/user-guide.fr) (fichier `docs/user-guide.fr.md`).

This guide explains how to make a short film with Video Producer. Interface labels are written in **bold**. Video Producer is delivered in steps. This version has the complete interface, in English and in French, but some functions are still simulated (chapter 15). A chapter about something that does not exist yet ends with "Available from step N". The administrator guide is a separate page that only admins see.

## 1. What Video Producer is

Video Producer is a PotionUI plugin for audiovisual editing, AI sequence generation, art direction, sound creation and 3D scene preparation, all in one page. You write a synopsis, split it into shots, generate quick draft takes, choose the best one, turn it into a final, then cut, match colors, mix sound and deliver. It opens from the **Video Producer** entry in the sidebar.

Before you start:

- An admin has to prepare at least one engine (this machine, a studio server or a cloud model) and at least one video preset assigned to you. If the Production bar shows no engine, see chapter 16.
- Your admin also sets the draft resolution and may limit the GPU minutes you can use per month.
- The model MiniMax-H3 comes with a license that excludes use, and anything generated with it, in the European Union, the United Kingdom, the United States and South Korea without an individual authorization from MiniMax, and that asks a commercial product to display "MiniMax H3" prominently. Ask your admin before you use it.

The interface is in English by default and also exists in French (chapter 13).

The page opens on a starter project, "Dawn at the harbour" ("Aube sur le port" in French), built in the language of the interface. It holds a synopsis, the global direction in five fields, five shots of 5 seconds still to generate, each with its shot prompt (the sleeping harbour, the fisherman's hands, the departure, the gulls, out to sea), a title, a marker named "Cast off" and four empty audio tracks. It has no media, no take, no reference and no 3D scene. Try the whole path on it, or start an empty project with **File › New project…**.

## 2. The path in eight steps

**Help › Getting started** shows the same path as a list you can click. The eight steps:

1. **Create a project.** **File › New project…** (or **File › Open…** for an existing one). In **Project properties…** you set the name, the aspect ratio (16:9, 2.39:1, 9:16, 1:1 or 4:5), the resolution (720p, 1080p or 4K) and the frame rate (24, 25 or 30 fps). Result: an empty project that is saved as you work.
2. **Set the global direction.** In the **Director IA** workspace, tab **Direction**: world and intent, characters and identity, photography, palette and lighting, pacing and continuity. Result: a text that guides every generation.
3. **Add the references.** In **Director IA**, tab **References**: identities, 3D sets and motion guides. Result: what must stay the same from one shot to the next.
4. **Split the film into shots.** In the **Storyboard** workspace: write the synopsis, click **Propose a breakdown**, keep the shots you want and adjust their shot prompts. Result: a row of shot cards.
5. **Generate drafts.** In the Production bar, quality **Draft**, then **Generate selection** (Ctrl+G). The estimate shows GPU time and quota. Result: draft takes A, B, and so on.
6. **Pick and make final.** In the Inspector, tab **Takes**: compare the takes, click the one the shot should play, then click **Final** on the best draft take. Result: the shot moves from Draft to Final.
7. **Edit, match and mix.** Fades on the clips, color match in the Inspector tab **Color**, the console in **Mix**. Result: a finished sequence.
8. **Prepare delivery.** **File › Export video…**, **Export to other software…** or **Export subtitles…**. Result: files you can download.

The interface of all eight steps is in place. In this version the page opens on the starter project (chapter 1) and the project lives in the page only: reloading the page loses your changes. **New project…** really starts an empty project, "Untitled project", and asks for confirmation first if the current project has unsaved changes. **Open…** is simulated (chapter 15). Available from step 3: saved projects. From step 4: drafts and finals. From step 6: delivery as video files.

## 3. The screen

The page has five levels of controls, from the widest to the most local, around a left panel, a center area, the Inspector and the timeline:

- **Menu bar.** Ten menus, in this order: **Video Producer**, **File**, **Edit**, **Cut**, **Shot**, **Production**, **Audio**, **View**, **Window**, **Help**. The **Video Producer** menu holds **About Video Producer**, **Preferences…**, **Keyboard shortcuts** and **Search commands…**. A menu shows "…" only when the command opens a window that asks for something, and a check mark in front of a state that is on. A gray flask icon marks a command that is simulated for now (**Open…**).
- **Project bar.** On the left, the button that shows or hides the side panel, the project name (click it to rename the project) and its save state ("Not saved" at first, "Modified · click to save" after a change, then "Saved at" and the time). In the middle, the workspace selector: **Media**, **Director IA**, **Storyboard**, **3D scene**, **Mix**. On the right, **Import**, **Export**, **Assistant**, a search button for the commands and the button that shows or hides the Inspector.
- **Production bar.** It targets what to generate and holds the only main button of the page, **Generate selection** (chapter 6).
- **Area headers and the timeline toolbar.** A title and counters on the left, small icons on the right.
- **Content.** Small buttons that appear when you hover or select.

A rule to remember: every other entry point (Storyboard, side panel, Director IA) only targets what to generate; the Production bar is the one that acts.

The ten menus group all the commands of the page. The command search (**Search commands…**, Ctrl+K) finds any of them by name, shows its menu and its shortcut, and runs it with Enter.

| Menu | What it holds |
|---|---|
| **Video Producer** | About, Preferences, Keyboard shortcuts, command search. |
| **File** | New project, Open, Save, Import files, From the PotionUI gallery, Project properties, the three exports. |
| **Edit** | Undo, Redo, Copy, Paste, Duplicate, Delete, Search media. |
| **Cut** | The three tools, Split at playhead, trims, Change duration, in and out points, Clear range, Add marker, Add title, Fade in and out. |
| **Shot** | New shot, Info, Show source, Shot takes, Make take final, Shot color, Match color to previous shot, Camera keyframes, Favorite, Reject, Remove flag. |
| **Production** | Global direction, Split synopsis into shots, Continuity check, Generate selection, Draft and Final quality, the queue, Results and takes, Assemble chosen takes, Advanced workshop, the engine, the Hybrid builder. |
| **Audio** | Add audio track, Import audio file, Mixing console, Voice and dialogue and the sound design workshop. |
| **View** | Play, loop, full screen, framing guides, Compare takes, Luminance scope, Audio meters, timeline zoom, Snapping. |
| **Window** | The five workspaces, the reference spaces, Side panel, Inspector, PotionUI assistant, Prompt library, Timeline index, Background tasks. |
| **Help** | Getting started, Keyboard shortcuts, Search features, Simulated features. |

### The areas of the page

- **Left panel.** It changes with the workspace (chapter 4). Show or hide it with the first button of the project bar or with Ctrl+Alt+1.
- **Center.** The viewer, the storyboard cards, the board of references or the 3D view, depending on the workspace.
- **Inspector.** On the right. It follows the selection (chapter 5). It starts hidden when the window is narrower than 1360 pixels: open it with the last button of the project bar, or select something, which opens it.
- **Timeline.** At the bottom. In **Mix**, the mixing console takes its place and a button brings the timeline back. Drag the thin line above the Production bar to give it more or less height.
- **Status bar.** At the very bottom, from left to right: the language reminder (`EN` or `FR`; click it to open the Preferences), the number of shots with the duration, the resolution and the aspect ratio, the active tool, the selection, the range. On the right: the number of direction points to check (click it to open the **Direction** tab), the generation queue, snapping and, when your admin has set a limit for you, your **GPU quota**, the minutes used this month out of that limit (cloud providers are billed separately).

The viewer has its own transport bar: monitor volume, go to the start, previous and next frame, play, loop, the timecode, framing guides, aspect ratio, resolution and full screen. When you preview a take, a comparison or a source media, a pill at the top of the viewer brings you **Back to the sequence**.

The timeline has a toolbar and one row per kind of item. The toolbar holds **Undo** and **Redo**, the **Select tool**, **Range tool** and **Blade tool**, **Split at the playhead**, **Duplicate**, **Delete**, the **Add** menu (**Prompt**, **Reference frame**, **Control video**, **Title**, **Marker**, **Audio track**), **Snapping**, the zoom and **Fit**. The rows are **Titles**, **Prompts**, **Frames**, **Control video**, **3D shot**, **V1 · Video** and one row per audio track, with **M** (mute) and **S** (solo). Click the ruler to move the playhead; with the Range tool, or by dragging with Alt held, draw a range. Drag a shot to change its order, drag its edges to trim it (the shots after it follow), drag the white handles at the top of a clip to set its fades, drag an audio clip to another track. Ctrl and the mouse wheel zoom. Double-click an empty spot of the Prompts, Frames or Control video row to create an item there.

## 4. Workspaces

Each workspace changes the left panel and the center. The Inspector on the right follows your selection in all of them. **Window › Timeline index** lists the prompts, frames, markers and Control videos with their time, and **Window › Background tasks** shows the generation in progress and the queue.

### Media

The media of the project in one panel. A new project has none: the panel says "No media in this project." and offers **Import media**, like the import button of its header and **Import** in the project bar. Import is simulated for now: it adds a placeholder media with no image. Importing from your PotionUI gallery and your files comes with step 3. Filter with the collection pills (**All**, **Images**, **Videos**, **Audio**, **Generated**), search by name without worrying about accents, double-click to preview, drag to the timeline. For a selected item the panel shows its duration, format and collection, and the buttons **Preview**, **Add to cut** and, for images and videos, **Use as frame at the playhead**. The center is the viewer.

### Director IA

The left panel has three tabs. A dot on **Direction** warns that there are points to check, and **Results** shows the number of takes.

- **Direction.** Shows what guides the generation for the current range: the global direction, the shot prompt, the references and Control videos, with **View the generation summary**. Below, **To check**, the list of direction conflicts and color matches to fix, the **Project H3 profile** (FL2VA, Ref2VA or Hybrid AV, chapter 9) and the **Global direction** itself, in five fields (world and intent, characters and identity, photography, palette and lighting, pacing and continuity), with a counter out of 4000 characters. Each field has a **Library & assistant** link. The gear button, **H3 settings**, opens the **Advanced workshop**.
- **References.** Three families, **Images and identity**, **3D sets** and **Motion guides**. A reference is global (it goes with every generation) or applies to a range only; **Attach to range** sets the second. **Reference** adds one. The center shows the board of references, in two groups, **Global direction** and **On the timeline**, with a search field. Drag a thumbnail onto the Frames track to anchor it to a precise moment. A new project has no reference: the board says so, and **Reference** adds the first one.
- **Results.** The takes of each shot, **Compare**, **Retake**, **Use**, the **Generation queue** and **Assemble chosen takes**.

### Storyboard

On the left: the **Synopsis** (one sentence becomes one shot) and **Propose a breakdown**. The **Proposed breakdown** lists the shots: tick the ones to keep, rename them and click **Add N shots at the end**. In this version the breakdown is simulated: it only cuts the synopsis into sentences. Then **To produce**, with **Drafts left** and **Move to final** (the time they will take), and **Continuity**, which lists the color matches to check, each with **Match color**.

In the center: one card per shot, in order, with its number, its duration, its name, its stage (**Source**, **To generate**, **Draft** or **Final**), its number of takes and its shot prompt; click the prompt to write it. Drag a card to move it. The buttons of a card appear when you hover it or select it: the main one follows the stage, **Generate**, **Make final**, **See takes** or **Regenerate**, and three icons show the shot in the viewer, insert a shot after it and delete it. The header counts the shots per stage, adds one with **Shot** and sets the size of the thumbnails; a **New shot** tile at the end does the same. In this workspace, the Left and Right arrow keys move the selection to the previous or next shot.

### 3D scene

A new project has no 3D scene. In the left panel the **Scenes** list is empty: **Sample scene** creates a procedural point cloud, marked **Simulated**, and **Reference a Gaussian Splat file…** asks for the path of a file and adds it as a scene. Then come the **3D shots on the timeline** (**New 3D shot at the playhead**), the **Preset trajectories** (**Orbit**, **Dolly in**, **Rise**), the camera and its keyframes in the Inspector, and the **Outputs for generation**: **Capture a frame** and **Generate the Control video**. The center is the 3D view (before any scene it says "No 3D scene" and offers **Sample scene**): drag to orbit, scroll to change the distance, play to preview the trajectory. This workspace is partly simulated: see chapter 15.

### Mix

The **Sound design workshop**, the **Project sounds** (drag one to a track, or use its plus button to add it at the playhead), the **Roles** (**Dialogue**, **Music**, **Ambience**, **SFX**) with their number of tracks, and the mixing console, which takes the place of the timeline: faders, **M** and **S**, pan, equalizer, compressor, filter, reverb and delay sends, meters and an automation mode. The center is the viewer. The four tracks of a new project are empty, and **Project sounds** says "No sounds in this project." until you import one. In this version an imported sound is a placeholder that the console plays as a synthetic sound made in your browser; with your own audio files it plays them (chapter 11). The workshop and the automation curves are simulated: see chapter 15.

Your own media and saved projects: available from step 3.

## 5. Inspector

The Inspector follows the selection and its title tells what is selected: **Video shot**, **Audio clip**, **Title**, **Shot prompt**, **Reference frame**, **Control video**, **3D shot**, **Marker**, **Reference** or **Console strip**. For a shot it starts with a thumbnail, the name (click it to rename the shot), the stage and the times, and has three tabs:

- **Shot.** A shortcut to the next action (**Generate drafts**, or **Make take A final**), **Duration and source** (the duration, where the shot starts in its source and the length of the source), **Fades** (**In** and **Out**), the **Flag** (**None**, **Favorite** or **Rejected**) and three icons to split the shot in the middle, duplicate it and delete it.
- **Takes.** The takes of the shot, as **Final** and **Drafts** (chapter 7).
- **Color.** The luminance scope, the match with the previous shot, presets and fine settings (chapter 10).

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

## 6. Production bar and estimate

The Production bar reads like a sentence: a target (**Shot**, **Range** or **Sequence**), the range with the number of shots and prompts it holds, a quality (**Draft** or **Final**), an output mode, an engine, the **Advanced workshop**, then the estimate, **Add to queue** and **Generate selection**. A number with a warning icon after the counters is the number of direction conflicts in the range; click it to see them.

- The output mode **AI generation** is the real one. **3D render** and **3D render + AI** are simulated (chapter 15); with **3D render** the main button reads **Prepare the render**.
- The engine pop-up lists what your admin enabled: this machine, a studio server and cloud models. In this version it shows three placeholder engines: **This machine · RTX 4090**, **Studio server · 2 × RTX A6000** and **Cloud provider · H100 on demand**. On a narrow window the pop-up is hidden: choose the engine in the **Advanced workshop** instead.
- The **Advanced workshop** has three steps: **Sources and guides**, **Engine and Hybrid builder** and **Sound and delivery**. It opens from the bar, from **Production › Advanced workshop…** and, for the engine, from **H3 settings** in Director IA.

The estimate gives the GPU time, the memory and what is left of your quota. It sits on the right of the bar; hover it for the detail: the number of shots and variants, the resolution, the engine, the memory against the engine's and the quota or the cost.

- The time comes from your own past generations on this machine with the same preset, engine and resolution. It shows "—" when there is none yet.
- The memory is an estimate from the size of the model files, never a guarantee.
- The quota is your monthly Video Producer GPU minutes, shown as **GPU quota** in the status bar when your admin has set a limit for you; without a limit there is no quota figure. A cloud engine does not use it. Only admins see the cost of a cloud generation.

What blocks **Generate selection** (the button is disabled and the bar shows the first reason; hover it to see them all):

- no valid range;
- neither a global direction nor a shot prompt in the range;
- an empty shot prompt in the range;
- a 3D output mode with no 3D shot in the range;
- a spent quota ("GPU quota exceeded": switch to draft or use the cloud provider).

What only warns, without blocking: a memory estimate above what the engine has. The bar shows a warning ("N GB of VRAM needed, M GB available on …: switch to draft, lower the resolution or change engines") and the generation goes on. The FL2VA profile with no frame in the range warns as well: "No frame in the range: the shots will be generated from text only." The generation goes on, from text only.

While a generation runs the bar shows the step and the progress, with **Pause** (then **Resume**) and **Cancel**. When it ends, a button tells how many takes are ready and opens the results. **Add to queue** keeps the current range for later: the queued windows are listed under **Generation queue** in Director IA, tab **Results**, and counted in the status bar.

In this version the engines are placeholder engines and the generation is simulated: the figures of the estimate are indicative, the progress is a simulation and no GPU is used (chapter 15).

Available from step 4: real generation, the engines your admin enabled, the time measured on your own generations, your real monthly quota and, for admins only, the cloud cost. The warning for a memory estimate above the engine's then reads "will stream through host RAM, slower".

## 7. Takes and final

A take is one generated video for one shot.

- Drafts are made at the resolution your admin chose (832×480 unless changed). The frame rate of a take is set by the preset (Wan 16 fps, MiniMax-H3 24 fps). The timeline and the exports use the frame rate of the project.
- Several variants are made per shot: A, B, and so on. They are listed in the Inspector, tab **Takes** (as **Final** and **Drafts**), and in Director IA, tab **Results**. Click the eye icon to preview one in the viewer, use **Compare** on two takes to see them side by side.
- Click a take in the Inspector, or **Use** in the Results tab, to make it the take the shot plays; it then shows a check mark, or **Used**. The flag button (**Mark for retake**) flags a take you want to redo, and the take then shows **Retake**. **Instructions used** opens the exact instructions behind a take: the global direction, the shot prompts, the references and Control videos, the profile, the mode and the seed.
- **Final** on a draft take makes it final. By default the take is upscaled with SeedVR2, to 720p, 1080p, 1440p or 2160p. **Re-render**, the secondary action, generates the shot again at the highest resolution of the preset, with the same seed. The new take says which one it comes from ("from A").
- **Assemble chosen takes** (Results tab) puts the takes you chose into the cut.

In this version the takes are simulated: each take shows a procedural thumbnail, the number of the shot on a gradient, marked **Simulated** (chapter 15).

Available from step 4.

## 8. Assistant

The **Assistant** button, **Window › PotionUI assistant** and Ctrl+J open the PotionUI chat, in the **Video Producer** mode. The assistant can:

- write the prompt of the selected shot;
- fix the contradictions between the global direction and the shot prompts;
- split your synopsis into shots;
- check the continuity between shots.

Every change to the project asks for your approval before it is applied. The assistant knows the workspace you are in, your selection, the playhead, the range, the global direction, the synopsis and the state of the production. It needs your admin to have set up a language model.

In this version the button, the menu and the shortcut already open the PotionUI chat, and so do the links **Ask the PotionUI assistant** (prompt library) and **Ask the assistant** (sound design workshop). The four actions above arrive with step 5.

Available from step 5.

## 9. Prompts: library and composer

The window **Prompt library & assistant** opens from **Window › Prompt library**, or from the **Library & assistant** links placed near a text (in the fields of the global direction, in the Inspector for a shot prompt and in the window that edits a shot prompt). It writes into a target, shown under its title: one of the five fields of the global direction, or a shot prompt. Opened from the menu it has no target and copies the prompt to the clipboard (**Copy the prompt**). The window has two tabs, **Library** and **Composer**, and a link, **Ask the PotionUI assistant**, that closes the window and opens the PotionUI chat. The templates, the categories and the composer choices exist in English and in French and follow the language you chose (chapter 13).

- **Library.** Five libraries, **Built-in**, **Personal**, **Project**, **Favorites** and **History**, and nine categories (Cinema, Camera, Lighting, Film styles, Dialogue, Photography, Sound, Continuity, To avoid). Search by name, description or keyword; the star marks a favorite. Each template says which H3 profiles it suits. A template can have variables, such as the subject or the place, that you fill in before inserting it. The **Editable preview** can also be edited by hand. **Save to Personal** keeps your version, and every inserted text goes to **History**. A new project starts with the built-in templates and one personal template; **Project**, **Favorites** and **History** are empty until you star a template or insert a text.
- **Composer.** Builds a prompt from four parts, **Camera movement**, **Lighting**, **Film style** and **Dialogue or acting intent**, for the H3 profile you pick (it starts from the profile of the project). Choose one option per part, or type your own in **Other…**, and fill in the subject, the action, the place and the emotion. The **Final prompt** stays editable, and **Recompose from the choices** brings it back. **Required references** tells whether the range has what the profile needs. When a Control video covers the range, the camera part is **Set by the Control video** and locked.
- **Insert** writes the text into the target: **Add to the text** adds it to the existing text, **Replace** replaces it.

The three H3 profiles and what each one asks for on the range:

| Profile | Meaning | It asks for |
|---|---|---|
| FL2VA | Continuity between the start and end images. | Start and end frames in the range. Without any frame, the shots are generated from text only. |
| Ref2VA | Keep the identity of the references during the action. | An identity reference (character, object). With MiniMax-H3 the generation follows the references once it is real (from step 4). |
| Hybrid AV | The soundtrack, rhythm and dialogue drive the picture. | An existing audio track in the range (dialogue or music). |

When a Control video is present, the motion comes from the guide.

## 10. Color and continuity

An alert appears only when two neighbor shots do not match: "“Shot” is brighter, darker, warmer or cooler than the previous shot". It shows in Director IA (tab **Direction**, under **To check**), in the Storyboard (under **Continuity**, and as a warning icon on the card of the shot) and in the Inspector. **Match** fixes it in one click by adjusting exposure and temperature to the previous shot. The measure is made on the real thumbnails of the takes. The **Color** tab also has the luminance scope, six presets (Original, Golden light, Cold morning, 35 mm film, Blue night, Soft) and fine settings (**Exposure**, **Contrast**, **Saturation**, **Temperature**), with **Reset** and **To all shots**. Before a shot has an image, the tab says that color can be adjusted once the shot is generated.

In this version the measure is already made, on the image of each shot that has one. The starter project has none yet, and the Storyboard then says "No match to check yet: the shots have no image." A similarity percentage between two generated shots can also appear in the alerts ("Check the identity between … and … (similarity 78 %)"): it is simulated (chapter 15). Color is real.

Available from step 6.

## 11. Audio and subtitles

Audio lives in tracks, each with a role: Dialogue, Music, Ambience or SFX. **Audio › Add audio track** and **Audio › Import audio file…** bring sounds in; **Audio › Mixing console** shows the console. In the console each strip has a role, effects (**Equalizer**, **Compressor**, **Filter**; **+ effect** adds one), sends to the reverb and delay buses (R and D), pan, a fader (double-click it to go back to 0 dB), a meter, **M** and **S** and an automation button; the auxiliary buses and the **Master** follow. The pills at the top show one role only. **Voice and dialogue…** and the sound design commands (**Ambience…**, **Foley…**, **Texture…**, **Impact…**, **Musical intent…**) open the **Sound design workshop**, which is simulated (chapter 15). The text of a dialogue is real: it feeds the subtitles, together with the titles of the timeline.

In this version the four tracks of a new project are empty and the sounds you import are placeholders. The console plays them as synthetic sounds made by your browser, so that you can try the faders, mute and solo, pan, equalizer, compressor, filter and sends and watch the meters.

Available from step 3.

## 12. Exports

**File › Export video…** opens **Export and share**, with three tabs:

- **Video.** Pick a format, a resolution and the extent (**Whole sequence** or **Range**), and say whether to add the audio stems. The formats are **Master file · ProRes 422**, **Web · H.264 MP4**, **Social media · vertical H.264** and **Archive · H.265**. The real export writes H.264 MP4 or VP9 WebM; ProRes 422, H.265 and the audio stems stay simulated and carry the badge.
- **To other software.** Final Cut Pro (`.fcpxml`), OpenTimelineIO (`.otio`) and EDL CMX 3600 (`.edl`). They are real files.
- **Subtitles.** An SRT file built from the dialogue text and the titles. **File › Export subtitles…** opens this tab.

Before the export, the window warns about shots that are not final yet, takes flagged **Retake** and direction conflicts that are not solved. Exports are written to your PotionUI storage, in a `video_producer/exports/` folder, and you download them from the page. Your admin sets a size budget for that folder per user.

In this version only the last two tabs produce files. Their button (the word "Download" followed by the file name, which comes from the project name) builds the file in your browser and saves it through the browser: nothing is written to your PotionUI storage. The media paths inside the Final Cut Pro, OpenTimelineIO and EDL files are made from the names of the media, not paths of real video files, and a shot without media becomes a gap. The **Video** tab shows a progress bar and ends with a note saying that no video file is written at this stage.

Available from step 6.

## 13. Language

Video Producer exists in English and in French. Choose **English** or **Français** in **Video Producer › Preferences…**, setting **Language**, or click the `EN` or `FR` reminder at the left of the status bar, which opens the same window. The change is immediate and is saved for you alone, on the server; if the saving fails, a message says that the language changed for this session only. Until you choose, the page follows the language of your browser (French if it is French, English otherwise).

The **Preferences** window has four other settings: **Preview quality** (**Best performance**, **Balanced** or **Best quality**, without effect yet), **Snapping by default**, **Framing guides** and **Single-key shortcuts** (chapter 14). They apply to the current session and are not saved.

What is translated: the menus, the windows, the buttons, the tooltips, the messages, the names given to new items (for example a new shot or a new track), the prompt library with its templates, categories and composer choices, and the way numbers and durations are written. What is never translated is the content of your project: your own texts (the synopsis, the global direction, the shot prompts, the names and titles you typed, the project name) and the starter project, which is built in the language of the interface when the page opens and is not translated afterwards. Product terms such as Director IA, Storyboard, Control video or FL2VA are the same in both languages.

## 14. Keyboard shortcuts

The table gives the shortcuts for Windows and Linux. On a Mac, read ⌘ for Ctrl, ⌥ for Alt and ⇧ for Shift; the menus and the tooltips show the notation of your system, and the side panel is ⌃⌘1 (Control and Command). **Search commands…** (Ctrl+K) finds any command, and **Keyboard shortcuts** (Ctrl+Alt+K) lists those that have a shortcut.

| Shortcut | Action |
|---|---|
| Ctrl+K | Search commands… |
| Ctrl+Alt+K | Keyboard shortcuts |
| Ctrl+, | Preferences… |
| Esc | Close, in this order: the command search, the open window, the open menu, a take preview or comparison; otherwise clear the selection |
| Ctrl+Z, Ctrl+Shift+Z | Undo, Redo |
| Ctrl+S | Save |
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

- Only while the focus is on the page and not in a text field. With a text field focused, a window open or the command search open, the other shortcuts are off; Esc, Ctrl+K and Ctrl+Alt+K always act. While the PotionUI chat is open, the shortcuts of the page are off.
- The menus and the **Keyboard shortcuts** window also show other combinations, for example Ctrl+N, Ctrl+O, Ctrl+C, Ctrl+V, Ctrl+F or Ctrl+1 to Ctrl+5 for the workspaces. They are not active in this version: use the menu, the buttons or the workspace selector.

## 15. What is simulated

Some parts keep their interface but do not do the real thing yet. They carry a gray dashed badge, **Simulated**, never a yellow one: yellow is kept for real points to check. **Help › Simulated features** opens the list.

The badge appears in the header of the windows **Open a project**, **Import media**, **Import an audio file**, **Reference a Gaussian Splat file** and **Sound design workshop** (titled **Voice and dialogue** for a voice); next to the formats **Master file · ProRes 422** and **Archive · H.265**, next to the audio stems and in the footer of the **Video** tab of the export window; on the automation button of the console strips; on the **Sample scene** and on the preview of a Gaussian Splat file in the 3D scene; and on a generated take, in the viewer ("Final take · simulated AI", "720p draft · simulated AI") and on its thumbnail. A gray flask icon marks the command **Open…**, and a few notifications are flagged the same way.

Already working in this version: editing on the timeline (trim, fades, split, snapping, range, markers, undo and redo), the selection and the Inspector, the Storyboard, the prompt library and the composer, the direction conflict checks, the color match, **File › New project…**, the camera, the trajectories and the keyframes of the 3D scene, the mixing console, and the Final Cut Pro, OpenTimelineIO, EDL and SRT files, which are real files.

The window **Simulated features** lists nine items. For each one, the table says what it does in this version and what it becomes once all the steps are delivered.

| Item in the window | In this version | Once all the steps are delivered |
|---|---|---|
| **AI generation and 3D render** | Progress, steps and takes are simulated: each take shows a numbered procedural thumbnail marked "Simulated". The estimates of time, memory, quota and cost are indicative. | Takes are real video files made by the engine you pick (this machine, a studio server or a cloud model); progress and errors come from the engine. The estimate shows GPU time (from your own past runs here, "—" when there is none), memory, your monthly quota and, for admins only, the cloud cost. **Final** upscales the chosen take with SeedVR2 by default; **Re-render** generates it again at the highest resolution of the preset with the same seed. With MiniMax-H3, the Ref2VA profile really conditions the generation on your references. Available from step 4. The 3D render modes stay simulated. |
| **Synopsis breakdown** | One sentence becomes one shot. | The assistant proposes the breakdown. Available from step 5. |
| **Identity check** | The similarity between shots is simulated. The color check really analyzes the images. | Color matching is measured on the real thumbnails of the takes (from step 6). The similarity percentage stays simulated, because no identity measure is available to plugins. |
| **Video render** | No video file is written. The Final Cut, OTIO, EDL and SRT exports produce real files. | H.264 MP4 or VP9 WebM videos assembled with ffmpeg and written to your storage. ProRes 422, H.265 and audio stems stay simulated: PotionUI's video converter writes H.264 MP4 or VP9 WebM only, and no per-role audio render exists. Available from step 6. |
| **Import, opening a project** | Import adds a placeholder media with no image; opening a saved project comes in a later step. | Import goes through PotionUI's pickers, the gallery shows your own media, projects are saved. Available from step 3. |
| **Gaussian Splat** | The referenced file is not loaded; the sample scene is a generated point cloud. | Stays simulated: the scene stays a 2D point preview and Gaussian Splat files are referenced, not loaded. |
| **Control video** | Computing the guide from the 3D scene is simulated. | Stays simulated: the guide video is not rendered from the scene, an imported Control video is not sent to an engine and the 3D capture is not rendered from the scene. The production modes **3D render** and **3D render + AI** depend on that guide and stay simulated. |
| **Voice and sound design** | Preparation is simulated; the preview is a simple synthesis. | Stays simulated: voice, character and timbre settings do not produce speech, lip sync has no separate step (MiniMax-H3 makes picture and sound in one pass) and no preset prepares ambience, foley, texture, impact or music for the workshop. The text of the dialogues does feed the subtitles for real. |
| **Edit audio** | Real-time synthesis (WebAudio): faders, mute and solo, pan, equalizer, compressor, sends and meters really work, on synthetic sounds. | The console plays your real audio files. Available from step 3. The automation curves stay simulated: the automation button only switches a mode, no curve is recorded. |

The window does not list the controls of the **Advanced workshop** that a preset does not declare: consistency between windows, lock character identity, motion guide first, the Hybrid builder and its saved profiles, audio / picture offset, follow the rhythm of the cut, guidance, overlap, window length, LoRAs, post-processing, the track that drives the performance, lip sync, result naming and insert variant A automatically. They are visible but do not drive any generation: a preset only exposes the controls it declares, and MiniMax-H3, for example, has no guidance and no negative prompt. With real engines they stay visible, grayed and marked simulated.

The assistant, for its part, is not simulated: it is the PotionUI chat in Video Producer mode, which writes shot prompts, fixes conflicts with the global direction, splits a synopsis into shots and checks continuity, and you approve each change before it touches the project (available from step 5).

## 16. Troubleshooting

- **The Production bar shows no engine.** Your admin has not finished the setup: an engine, a video preset assigned to you. Ask them to open Admin → Plugins → Video Producer.
- **The estimate shows "—" for the time.** Nothing has been measured yet for this preset, engine and resolution on this machine. It fills in after a few generations.
- **"Will stream through host RAM, slower".** The memory estimate is above what the engine has. The generation is not blocked. If the server lacks free memory for it, the engine refuses to start and the take fails with an error.
- **The quota is spent.** **Generate selection** is refused until the next month or until your admin raises the limit of your plan. Running generations are not stopped.
- **Generate selection is disabled.** Read the message in the bar: no range, no direction and no shot prompt, an empty prompt, a 3D mode with no 3D shot, or the quota.
- **A warning says the shots will be generated from text only.** The FL2VA profile has no frame in the range. Add a start or an end frame, or pick another H3 profile; the generation is not blocked.
- **References are ignored with MiniMax-H3.** Ask your admin to check the model file picked for the References mode.
- **A take failed.** The message and its code are shown on the take. If PotionUI was restarted during the generation, the take is marked failed and the generation cannot resume: start it again.
- **An export fails.** Ask your admin about ffmpeg, or free some of your exports: the folder has a size budget.

Available from step 4. Exports from step 6.

## 17. Glossary

| English | Français | Meaning |
|---|---|---|
| shot | plan | A clip of the film, one generation. |
| take | prise | One generated version of a shot. |
| draft | brouillon | A fast, lower-resolution take to judge motion and framing. |
| final | final | The chosen take, upscaled or re-rendered. |
| match | raccord | Making two neighbor shots look alike (color) or keep the same identity. |
| fade | fondu | A gradual start or end of a clip. |
| playhead | tête de lecture | The current position on the timeline. |
| range | plage | A part of the timeline between an in point and an out point. |
| global direction | direction globale | The text that guides every generation. |
| shot prompt | instruction locale | The text for one shot; it completes the global direction. |
| Control video | Control video | A guide video that sets the motion. |
| H3 profile | profil H3 | FL2VA, Ref2VA or Hybrid AV: what guides the generation. |
