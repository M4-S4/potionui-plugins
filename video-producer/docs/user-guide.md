# Video Producer: user guide

Français : [Video Producer : guide utilisateur](/docs?doc=plugin/video-producer/user-guide.fr) (fichier `docs/user-guide.fr.md`).

This guide explains how to make a short film with Video Producer. Interface labels are written in **bold**. The interface is complete, in English and in French. Your projects are saved as you work, your media are imported from PotionUI, and takes and finals are real videos (chapters 8 and 9). The PotionUI assistant has its own mode (chapter 10), shots are joined at their seams (chapter 12), and delivery is real: videos for the web and for social networks, files for other software and subtitles (chapter 14). The administrator guide is a separate page that only admins see.

## 1. What Video Producer is

Video Producer is a PotionUI plugin for audiovisual editing, AI sequence generation, art direction and sound creation, all in one page. You write a synopsis, split it into shots, generate quick draft takes, choose the best one, turn it into a final, then cut, match colors, mix sound and deliver. It opens from the **Video Producer** entry in the sidebar.

Before you start:

- An admin has to prepare at least one engine (this machine, a studio server or a cloud model) and at least one video preset assigned to you. If the Production bar shows no engine, see chapter 17.
- Your admin also sets the draft resolution, how many generations you can have in progress at once, and may limit the GPU minutes you can use per month.
- Generation is real: the takes are videos made by your admin's machines or cloud account, and they take time. The estimate in the Production bar tells you what to expect before you start (chapter 8). As a measure, on a 12 GB graphics card a 5-second draft took about 6 to 7.5 minutes with the presets named (12 GB) and about 26 minutes with Wan, and a final by upscale to 1080p took more than two hours.
- The machine your admin runs decides what you can use. A preset whose name ends with a card size is set up for a graphics card of that size, and the engine pop-up adds the ordinary memory (RAM) the server needs (chapter 8). On an 8 GB card, pick **Wan 2.1 T2V 1.3B (8 GB) · 32 GB RAM** or **Wan 2.2 TI2V 5B (8 GB) · 32 GB RAM**: they make 480p clips of up to 5 seconds from the text alone. On a 12 GB card, pick **MiniMax H3 (12 GB) · 64 GB RAM** or **MiniMax H3 Fast (12 GB) · 64 GB RAM**: the other MiniMax H3 presets are made for bigger cards (the Fast one ran out of memory on a 12 GB card in our tests). Ask your admin which card they have.
- Delivering a video file needs ffmpeg on your PotionUI server. If the export window says that ffmpeg is missing, ask your admin (chapters 14 and 17). The files for other software and the subtitles do not need it.
- The assistant needs a language model that your admin has configured in PotionUI and assigned to you (chapter 10). Ask your admin to connect a local model server set up for the assistant (llama.cpp `llama-server` or Ollama) or an online provider: the model built into PotionUI ran out of memory or could not call the tools on a 12 GB graphics card in our tests. Everything else works without it.
- The model MiniMax H3 (the **MiniMax H3** entries of the engine pop-up) comes with a license that excludes use, and anything generated with it, in the European Union, the United Kingdom, the United States and South Korea without an individual authorization from MiniMax, and that asks a commercial product to display "MiniMax H3" prominently. Ask your admin before you use it. Video Producer does not check any of this for you.

The interface is in English by default and also exists in French (chapter 15).

The first time you open the page, it creates a starter project, "Dawn at the harbour" ("Aube sur le port" in French), and opens it. It holds a synopsis, the global direction in five fields, five shots of 5 seconds still to generate, each with its shot prompt (the sleeping harbour, the fisherman's hands, the departure, the gulls, out to sea), a title, a marker named "Cast off" and four empty audio tracks. It has no media, no take and no reference. Its name, synopsis, shot names, title and marker are written in the language of the interface; its global direction and shot prompts are written in the prompt language of the project, English by default (chapter 15). Try the whole path on it, or start an empty project with **File › New project…**. On your next visits the page opens the project you used last (chapter 5).

## 2. The path in eight steps

**Help › Getting started** shows the same path as a list you can click. The eight steps:

1. **Create a project.** **File › New project…** (or **File › Open…** for an existing one). In **Project properties…** you set the name, the aspect ratio (16:9, 2.39:1, 9:16, 1:1 or 4:5), the resolution (720p, 1080p or 4K) and the frame rate (24, 25 or 30 fps). Result: an empty project that is saved as you work.
2. **Set the global direction.** In the **Director AI** workspace, view **Direction**: world and intent, photography, palette and lighting, pacing and continuity; the recurring characters and places are cards of the **Bible** view. Result: a text that guides every generation.
3. **Add the references.** In **Director AI**, view **References**: identities, sets and motion guides. Result: what must stay the same from one shot to the next.
4. **Split the film into shots.** In the **Storyboard** workspace: write the synopsis, then click **Propose a breakdown** (one sentence becomes one shot) or ask the assistant to cut it (chapter 10), keep the shots you want and adjust their shot prompts. Result: a row of shot cards.
5. **Generate drafts.** In the Production bar, pick the **Generation engine**, quality **Draft**, then **Generate selection** (Ctrl+G). The estimate shows time, memory and quota. Result: real draft takes A, B, and so on, made by the engine you picked.
6. **Pick and make final.** In the **Review** view of Director AI, or in the Inspector, tab **Takes**: compare the takes, label the ones worth keeping **Candidate** and the others **Reject**, click **Final** on the one the shot should play, then click **Make final** on that draft to get it at full resolution. Result: the shot moves from Draft to Final.
7. **Edit, match and mix.** Fades on the clips, color match in the Inspector tab **Color**, seam frames between shots (chapter 12), the console in **Mix**. Result: a finished sequence.
8. **Prepare delivery.** **File › Export video…**, **Export to other software…** or **Export subtitles…**. Result: a video in your library and files you can download.

All eight steps work for real, and your projects are saved as you work (chapter 5). The page opens the project you used last, or the starter project the first time (chapter 1). **New project…** starts an empty project, "Untitled project", and adds it to your projects. Drafts and finals are real videos made by your admin's engines. Delivery is real: the web and social videos, the ProRes master, the H.265 archive, the audio stems and the files for other software (chapter 14).

## 3. The screen

The page has five levels of controls, from the widest to the most local, around a left panel, a center area, the Inspector and the timeline:

- **Menu bar.** Ten menus, in this order: **Video Producer**, **File**, **Edit**, **Cut**, **Shot**, **Production**, **Audio**, **View**, **Window**, **Help**. The **Video Producer** menu holds **About Video Producer**, **Preferences…**, **Keyboard shortcuts** and **Search commands…**. A menu shows "…" only when the command opens a window that asks for something, and a check mark in front of a state that is on.
- **Project bar.** On the left, the button that shows or hides the side panel, the project name (click it to rename the project) and its save state ("Saving…", "Saved at" and the time, "Modified · click to save" or "Not saved — retry"; chapter 5). In the middle, the workspace selector: **Media**, **Storyboard**, **Director AI**, **Mix**, **Play**. On the right, **Import** (a menu with **From the library…** and **From this computer…**, chapter 6), **Export**, **Assistant** (it opens the PotionUI chat, chapter 10), a search button for the commands and the button that shows or hides the Inspector.
- **Production bar.** It targets what to generate and holds the only main button of the page, **Generate selection** (chapter 8). It shows in **Storyboard** and **Director AI** only; Ctrl+G queues from every workspace, even while takes are running.
- **Area headers and the timeline toolbar.** An icon, a title and a counter on the left, small icons on the right. The headers, the rows of tabs and the timeline toolbar are all 40 pixels high.
- **Content.** Small buttons that appear when you hover or select.

A rule to remember: every other entry point (Storyboard, side panel, Inspector, Director AI) only targets what to generate; the Production bar is the one that acts.

The ten menus group all the commands of the page. The command search (**Search commands…**, Ctrl+K) finds any of them by name, shows its menu and its shortcut, and runs it with Enter.

| Menu | What it holds |
|---|---|
| **Video Producer** | About, Preferences, Keyboard shortcuts, command search. |
| **File** | New project, Open, Save, Version history, Import from the library, Import from this computer, From the PotionUI gallery, Project properties, the three exports. |
| **Edit** | Undo, Redo, Copy, Paste, Duplicate, Delete, Search media. |
| **Cut** | The three tools, Split at playhead, trims, Change duration, in and out points, Clear range, Add marker, Add title, Fade in and out. |
| **Shot** | New shot, Info, Show source, Shot takes, Shot editor, Make take final, Shot color, Match color to previous shot, Favorite, Reject, Remove flag. |
| **Production** | Global direction, Split synopsis into shots, Continuity check, Generate selection, Draft and Final quality, the generation queue, Cancel the generation, Results and takes, Assemble chosen takes, Make the film final, Edit Engine. |
| **Audio** | Add audio track, Import audio from the library, Import audio from this computer, Mixing console. |
| **View** | Play, loop, full screen, framing guides, Compare takes, Luminance scope, Audio meters, timeline zoom, Snapping. |
| **Window** | The five workspaces, Storyboard as a band, the four views of Director AI, the reference spaces, Side panel, Inspector, PotionUI assistant, Prompt library, Timeline index, Background tasks. |
| **Help** | Getting started, Keyboard shortcuts, Search features. |

### The areas of the page

- **Left panel.** It changes with the workspace (chapter 4); **Play** has none. Show or hide it with the first button of the project bar or with Ctrl+Alt+1.
- **Center.** The viewer, the storyboard or the view of Director AI, depending on the workspace.
- **Inspector.** On the right. It follows the selection (chapter 7). In Director AI, each of the four views shows its own panel in its place (chapter 4). It starts hidden when the window is narrower than 1360 pixels: open it with the last button of the project bar, or select something, which opens it.
- **Timeline.** At the bottom, except in **Director AI** and in the band of the Storyboard. In **Mix**, the mixing console takes its place and a button brings the timeline back. In the Storyboard grid, the Production bar sits above it. Drag the thin line above the timeline (above the Production bar in the Storyboard grid) to give it more or less height.
- **Status bar.** At the very bottom, from left to right: the language reminder (`EN` or `FR`; click it to open the Preferences), the number of shots with the duration, the resolution and the aspect ratio, the active tool, the selection, the range. On the right: the number of direction points to check (click it to open the **Direction** view of Director AI), the number of takes in the generation queue (click it to open the generation queue, chapter 8), snapping and, when your admin has set a limit for you, your **GPU quota**, the minutes used this month out of that limit (cloud providers are billed separately).

The viewer has its own transport bar: monitor volume, go to the start, previous and next frame, play, loop, the timecode, framing guides, aspect ratio, resolution and full screen. When the viewer is narrow, for example in Media or Mix between the two panels of a window 1280 pixels wide, the volume slider hides and only the mute button stays, so that nothing overlaps; the time buttons stay centred as long as there is room. When you preview a take, a comparison or a source media, a pill at the top of the viewer brings you **Back to the sequence**.

The timeline has a toolbar and one row per kind of item. The toolbar holds **Undo** and **Redo**, the **Select tool**, **Range tool** and **Blade tool**, **Split at the playhead**, **Duplicate**, **Delete**, the **Add** menu (**Prompt**, **Reference frame**, **Title**, **Marker**, **Audio track**), **Snapping**, the zoom and **Fit**. The rows are **Titles**, **Prompts**, **Frames**, **V1 · Video** and one row per audio track, named **A1**, **A2**… from top to bottom. **V1** and every audio track have **M** (mute) and **S** (solo) in their header (chapter 13). Click the name of an audio track to select it; right-click it, or press the Menu key or Shift+F10 on it, for its menu: **Track settings**, **Add an audio track** and **Delete track…**. A shot whose media is a video shows a speaker at the bottom left of its block when you hover it: click it to mute the sound of that shot, and it stays shown, crossed out, while the shot is muted. Click the ruler to move the playhead; with the Range tool, or by dragging with Alt held, draw a range. Drag a shot to change its order, drag its edges to trim it (the shots after it follow), drag the white handles at the top of a clip to set its fades, drag an audio clip to another track. The trim and fade handles are for the mouse; from the keyboard, use **Cut › Trim start to playhead**, **Trim end to playhead** and **Fade in and out**, or the **Duration and source** and **Fades** fields of the Inspector (chapter 7). Ctrl and the mouse wheel zoom. Double-click an empty spot of the Prompts or Frames row to create an item there.

## 4. Workspaces

Each workspace changes the left panel and the center. The Inspector on the right follows your selection in all of them but **Play**, which keeps only the viewer. The Production bar shows only in **Storyboard** and **Director AI**. **Window › Timeline index** lists the prompts, frames and markers with their time, and **Window › Background tasks** shows the generation in progress and the queue.

### Media

The media of the project in one panel. A new project has none: the panel says "No media in this project." and offers **Library** and **From computer**, with the line "Ctrl+I · Ctrl+Alt+I" under them, like the two import buttons of its header and the **Import** menu of the project bar; you can also drop files on it. Chapter 6 explains how to bring in your images, videos and audio files. Filter with the collection pills (**All**, **Images**, **Videos**, **Audio**, **Generated**), each with its count, on one row that scrolls when the panel is narrow; search by name without worrying about accents, double-click to preview, drag to the timeline. For a selected item the panel shows its duration, format, collection and origin, and the buttons **Preview**, **Add to cut** and, for images and videos, **Use as frame at the playhead**. The center is the viewer.

### Storyboard

The Storyboard has two views, chosen with **Grid** and **Band** in its header (Window › Storyboard as a band); it opens on the band.

#### The band

The band shows the shots to the time scale, so the rhythm of the cut can be read at a glance. At the top, a thin overview of the whole sequence: each shot in the color of its stage, a failed shot in red, a shot in progress striped, an orange tick on a seam to check, the dashed shots of a proposed breakdown and the visible window; click or drag it to scroll the band. Below it, aligned on the same time:

- **Song**: the ruler and the parts of the song, which are the markers (M) placed on it;
- **V1 · Shots**: one block per shot, as wide as its duration, with the thumbnail of its take repeated along the block, or its first and last frames around a hatched area while it has no take. The block carries its number and the chain chip (chapter 12), the progress of a take in progress (or **Queued**, or **Waiting** when it waits for the take of the previous shot), **Failed** when its latest take failed, **Prompt modified** or **No instruction**, its duration, the sliders icon of an own engine, the waveform icon of its sound and its cast. A marker on the junction of two shots shows the seam: green when it is measured, orange with the issues in its tooltip when it needs a look; click it to compare the two shots in the monitor;
- **Takes**: up to four takes stacked under each shot, the final on top, then the candidates, the drafts and the rejected takes (hatched), then the takes in progress, queued or failed; the takes of the selected shot show their letter and label. Click a take to see it in the monitor;
- **Music**: the waveform of the clips of the Music tracks;
- **Reference sounds**: under each shot, what it sends to its engine as a reference sound (reference tracks and sound references), green when the engine follows it, grey when it is mixed onto the take.

Drag a shot to move it; drag its right edge to change its duration: the next shots follow, the song stays in place, the magnet snaps the cut to the edges of the shots and sounds, the markers and the playhead, and the tooltip says where the cut falls. Ctrl and the mouse wheel zoom around the pointer. The header holds the magnet and the zoom as the timeline toolbar does, in the same order: the magnet, **−**, the slider, **+** and **Fit**; then **Shot**. A double click on a shot opens the shot editor.

A project with no shot shows, under the band, "No shot yet" with its text, **Synopsis and breakdown** and **Shot**, and the line "D opens Synopsis and breakdown". Neither button is a main button: **Generate selection** stays the only one.

Under the band, the **monitor** plays the cut like the viewer, with the end of the previous shot on its left and the start of the next shot on its right, each with the marker of its seam. With a take chosen in the stack, or with the Up and Down arrow keys, the monitor shows that take outside the cut, with **Rejected**, **Candidate** and **Final**, and Enter uses it. With a seam chosen, the monitor compares the last frame of the previous shot and the first frame of the shot side by side, with the issues and their actions (**Match color**, **Use the previous shot’s last frame**, **Compare the takes**) and the switch **Start from the end of the previous shot** (chapter 12). Under each image, **Shot 01 color** (or 02) unfolds the color settings of its shot: **Preset**, **Exposure**, **Contrast**, **Saturation**, **Temperature** and **Reset**. As soon as one is unfolded, or when the monitor is wide enough, the settings sit on either side of the images and scroll on their own, under the issues of the seam. Adjusting either shot keeps the view open: its image and the measure of the seam follow, and Ctrl+Z undoes one gesture at a time. Next to the monitor, the **quick edit** of the selected shot: its name, its prompt (a change marks the takes **Prompt modified**, as in the shot editor), its duration, its engine, its number of drafts, its key frames, its cast and its sound, the switch **Start from the end of the previous shot**, and **Shot editor**; to generate the shot, use the Production bar under the band (chapter 8). With no shot chosen, the quick edit reads "No shot chosen": "Pick a shot on the band to edit it here." The left panel and the timeline are hidden in this view, since the band holds their tracks; the Inspector closes when you open the band and comes back with the Inspector button.

#### Synopsis and breakdown

**Synopsis and breakdown** in the header of the band (D, Production › Synopsis and breakdown, or the left panel button) opens a window under the band, which stays in use. The button is plain, without a frame, and stays highlighted while the window is open. The window has three tabs:

- **Breakdown**: the synopsis, the names of the bible it contains, and three methods. **By sentence** is the former breakdown (one sentence, one shot of 3 to 7 s). **On the song** fills the parts of the song at the chosen average length (2 to 8 s) and spreads the sentences over them in order; it needs a song on a Music track. **Assistant** asks the PotionUI assistant, whose proposal comes back in the same list. Each proposed shot can be kept or not, renamed, given another prompt, made shorter or longer, split in two, merged with the next one, moved and removed; it takes the characters and the place of the bible its sentence names. The proposed shots appear dashed on the band and in the overview, at their duration and place, before anything changes. **Insert** places them at the end or after the selected shot; **Add N shots** (Ctrl+Enter) adds them, and Undo removes them.
- **To produce**: the drafts left and the shots to move to final, with **Generate their drafts**, the takes in the queue and the shots to do, each with **Show**.
- **To check**: the seams to check (with their actions), the failed takes (**Retry**), the shots whose prompt changed after their takes (**Generate new drafts**) and the shots without a prompt (**Write the prompt**), each with **Show**. The header button shows how many there are.

#### The grid

On the left: the **Synopsis** (one sentence becomes one shot) and **Propose a breakdown**. The **Proposed breakdown** lists the shots: tick the ones to keep, rename them and click **Add N shots at the end**. The breakdown of that button is simple: it only cuts the synopsis into sentences (its tooltip says "Sentence split; ask the assistant for a real breakdown"). The assistant makes a real breakdown and fills the same list (chapter 10). Then **To produce**, with **Drafts left** and **Move to final** (the number of shots and the footage still to do for each), and **Continuity**, which lists the color matches to check, each with **Match color** and **Use the previous shot’s last frame** (chapter 12).

In the center: one card per shot, in order, with its number, its duration, its name, its stage (**Source**, **To generate**, **Draft** or **Final**), its number of takes, **Edit** and its shot prompt. **Edit** opens the shot editor (below). On a shot without takes, clicking the prompt opens the shot editor too; once the shot has a take, its prompt is only shown, so that a click does not change what the takes were made from. When the shot was edited after its take was made, the thumbnail carries **Prompt modified** (the take on the shot, or every take when none is on it, is older than the edit). A sliders icon after the number of takes says that the shot sets its own engine; hover it for the detail ("Own engine: LTX-2.5 · Final · seed 42"). The block of the shot on the timeline carries the same icon. A waveform icon says that the shot sends sound with its generation (a sound reference or a reference track, chapter 13); hover it to read what its engine does with it: green, "Guides the generation: MiniMax H3 follows this sound."; grey, "Will be mixed onto the take, not used as a guide."; amber, "Ignored by this engine: the sound stays in the edit only." Drag a card to move it. The buttons of a card appear when you hover it or select it: **Make final** on a draft and **See takes** on a final, which opens the Inspector; on a shot **To generate** or **Source**, the number of drafts of the shot instead (×1 to ×8, chapter 8), since a card does not generate: select the shot, then use the Production bar. Three icons show the shot in **Play** (**Show in the viewer**, also a double click on the card), insert a shot after it and delete it. While a take of the shot is in progress, the card shows its step and progress, as the block of the shot does on the timeline, and its buttons are disabled; a take that waits for the take of the previous shot says "Waiting for take A of “Shot 2”" there. The number is followed by the chain chip (chapter 12). When the shot does not match the previous one, an orange alert button at the top right of the thumbnail opens the seam panel: the issues with their actions (**Match color**, **Use the previous shot’s last frame** or **Use the new last frame**, **Compare the takes** for an identity to check, which shows the two placed takes side by side in the monitor of the band), the switch **Start from the end of the previous shot** and **Compare the last and first frames in the monitor**, which switches to the band. While a seam has a light or color issue, **Match colors (n)** in the header of the grid and of the band fixes them all at once (chapter 12). The header counts the shots per stage, adds one with **Shot** and sets the size of the thumbnails; a **New shot** tile at the end does the same. When the shots do not fit in the window, the grid scrolls with the wheel and its scroll bar, under its header, which stays in place. In this workspace, the Left and Right arrow keys move the selection to the previous or next shot, the Up and Down arrow keys to the shot above or below, Home and End to the first and the last shot; the shot chosen with the keyboard, or from another view (the timeline, the band, the Review), is brought into view.

#### Picking several shots

Ctrl+click (⌘+click on a Mac) on a card of the grid, a shot of the band or a block of the V1 track of the timeline adds the shot to the selection, or takes it out. Shift+click picks every shot, from the chosen shot to that one, in the order of the edit; Ctrl+Shift+click adds them to the shots already picked. The picked shots have a thick outline and their number turns to the accent color, with a check. The header of the grid and of the band shows "3 picked" in place of the counts per stage, with a cross that clears the selection, and the target of the Production bar becomes **3 shots** (chapter 8). The Inspector, and the quick edit in the band, then show **Selection**: the number of shots, their total length, their stages and their list (click a shot to keep it alone), a reminder of the shortcuts and **Clear the selection**.

- Ctrl+G or **Generate selection** queues every picked shot, in the order of the edit, following the chain (chapter 12).
- Backspace or Delete deletes every picked shot in a single step, which **Edit › Undo** brings back.
- Esc, a plain click on a shot, or **Shot**, **Range** or **Sequence** in the Production bar clear the selection. **Shot › Pick every shot** and **Shot › Clear the selection of shots** do the same from the menu.
- The other commands (duplicate, split, the shot editor, the takes, make final) act on one shot: the active shot, the last one added with Ctrl+click, or the one a Shift+click starts from.

#### The shot editor

**Edit** on a Storyboard card, or **Edit shot…** in the Inspector, opens the window "Shot · <name>". It gathers what a take of the shot is made from:

- **Shot prompt text**, with **Library & assistant**. The warnings about the direction show under the text.
- **Cast**: the characters and the place of the shot, from the bible (chapter 4, The bible), with a warning when the shot prompt does not name a character you cast. Under it, **Prompt part from the references**: the part of the prompt made from the references and the cards of the shot, as it would go to the engine of the shot (with MiniMax H3 in Ref2VA, the subject definitions, the retention lines and the citations in the shot; with MiniMax H3 otherwise, the subject definitions; with LTX, Wan and the cloud models, the cards of the bible). **Replace for this shot** lets you edit it: your text is sent as it is instead of the composed one, and **Back to the composed text** undoes the replacement. When a reference or a card changes afterwards, the window says that the composed text changed and shows it; **Keep my text** keeps yours. Then **Prompt sent to the engine**: the whole prompt the shot would send with your changes, composed for the engine of the shot (its shot prompt, its cast and the global direction), with the warnings about its length.
- **Dialogue**: the lines of the shot, in order. **+ Line** adds one, said by the next character cast in the shot; for each line choose the **Speaker** (a character of the bible, or **Unnamed voice**), type the exact words, tick **Off-screen** for a voice heard outside the frame, and remove it with its cross. The counter compares the words with what the shot can carry at a natural pace (three words a second) and turns orange past it; a character who speaks on screen without being cast in the shot gets a warning too. MiniMax H3 and LTX speak the lines with the mouth in sync, in the voice and the language set on the character's card (see The bible); Wan and the cloud models leave them out, and the estimate says so. The prompt below shows the lines as they will be sent.
- **Duration**, at most the length of the media of the shot when it has one ("At most 5.0 s with the media of the shot.").
- **Frames**: the **First frame** and the **Last frame**. Click one to pick an image of the project, or **Library** or **From computer** to import one (chapter 6); **Remove** takes it off.
- **References**. **Inherited from the project** lists the global references, each with an **Exclude** box: an excluded reference is not sent with this shot, and the other shots keep it. **This shot only** lists the references of the shot, with their name and type; **Add to the shot** adds one from an image (of the project, the library or your computer), and the trash icon removes one. The line at the top counts the references the shot sends ("2 references for this shot"). An engine sends at most 9 images, 3 videos and 3 audio files per shot (chapter 8): the excluded ones leave room for the next ones. **Add a sound** adds a sound reference of the shot only (a sound of the project, **Library** or **From computer**), with its type, **Voice**, **Music** or **Ambience**; sounds show their length and a player. **Reference tracks** lists the audio tracks checked **Reference for the generation** (chapter 13), each with what it holds under the shot ("1 clip between 0.0 s and 5.0 s", or "Nothing between …: nothing is sent") and an **Exclude** box that leaves the track out for this shot only. The last line says what the engine of the shot does with its sound: "Guides the generation: MiniMax H3 follows this sound.", "Will be mixed onto the take, not used as a guide." or "Ignored by this engine: the sound stays in the edit only."
- **Start and end images** (folded until the shot has candidates): the start image of the shot, its end image or both, made by an image model from the pictures of the shot or taken from the shots around it. **Image to make** has two rows. **Made by the model**: **Start image**, **End image** or **Both**. Pick the **Image model**: every image preset of your instance is listed, those that can work here first (an edit preset such as Qwen-Image-2.1, which takes several pictures, or an image to image one such as Flux2 or Qwen-Image, marked “one picture”), then, greyed under **Not usable here**, the others with their reason (not fully installed, no edit or image to image mode, provider turned off, provider without an API key, no edit model turned on); the choice is kept for the project, and a choice that can no longer run says why. Choose 2 to 4 **Candidates** (**Per image** with **Both**). **Pictures sent, in this order** shows what goes, numbered, each with its tag: for an end image, the start image of the shot first, as the framing; then the sets, then the characters, objects and styles; the first picture is the one edited and gives its frame to the image, and those past the limit of the model are dimmed. The line below gives the time (once a candidate of this model was measured), the memory and the GPU quota, or the cost for an admin. **Make 2 candidates for the start image** (or **for each image**) starts them; each one is a candidate A, B… of the shot, which waits in the queue like a take and says whether it was made **For the start** or **For the end**. On a finished one, **Use as start** or **Use as end** puts it in the **Frames** of the window (save the shot to keep it), the thumbs-down icon rejects it, and the trash icon deletes it (its image stays in your history). A failed candidate has **Retry**. **Taken from the shots around**, without a model: **Retrieve from previous shot** takes the last frame of the previous shot as the start image, **Retrieve from next shot** the first frame of the next shot (or its own start image) as the end image, and **Both** does the two; **Retrieve** takes them, and a line says what each side gives, or that it is already in place. Retrieving from the previous shot also turns on **Start from the end of the previous shot** for this shot, the switch of Inspector › Frames: it is the same link. While the previous shot is still being generated, the button reads **Link to the previous shot**: the shot then waits for that take and starts from its last frame. An option is greyed, with its reason under the row, when the shot around has nothing to give: no media and no take, no previous shot for the first shot, no next shot for the last one. A warning says when the engine of the shot leaves an image out: the Ref2VA profile, an engine that generates from text only, an engine that takes no end image, or an end image without a start image. Save the shot to keep the images; Ctrl+Z then takes them back.
- **Drafts**: how many drafts a generation of the shot makes at once (chapter 8).
- **Engine**: what the shot generates with. Each field starts on the value of the project: **As the project (Wan 2.1 / 2.2)** for the engine, **As the project (FL2VA)** for the profile, **As the Production bar** for the quality, **Random** for the seed. Pick another value to give it to this shot only: **Preset or model** (the engines of the Production bar pop-up), **Profile** (the ones the chosen engine cannot generate are greyed), **Quality** (**Draft** or **Final**, whatever the bar says) and **Seed** (the arrows button picks one). With a seed, the first take of each generation takes it and the next ones the seeds after it, so generating again gives the same takes. **Back to the project** clears them all. A retry or a **Make final** keeps the engine and the seed of its take.

**Save** applies everything at once, and **Edit › Undo** brings it all back. When the shot has takes, the window says so ("This shot has 4 takes. Saving a change keeps them and marks them “Prompt modified”.") and, once you change the prompt, the duration, a frame or a reference, the footer warns "The takes of the shot will be marked “Prompt modified”". Saving deletes no take: they stay, with **Prompt modified** on their card and on the Storyboard card, until you generate new drafts. Changing only the number of drafts or the engine marks nothing. Editing the prompt of a shot elsewhere (the Inspector of the shot prompt, the prompt editor of the timeline, the library, or the assistant when you approve its rewrite) marks the takes the same way. If the assistant changes the shot while the window is open (a character, a reference, its prompt), **Save** keeps its change wherever you did not touch it; when you both changed the same setting, your version is kept and the page warns you.

A capture of the window, in the dark and light themes of the English interface, is in `docs/screenshots/shot-editor.png`, and one of its **Engine** section with settings of the shot's own in `docs/screenshots/shot-engine.png`.

### Director AI

Director AI shows one view at a time in the center: **Review**, **Direction**, **Bible** and **References**. It opens on **Review**, or on **Direction** while the project has no take yet, then keeps the view you chose. Alt+1, Alt+2, Alt+3 and Alt+4 open the four views from any workspace, as do the same commands of the **Window** menu. Director AI has no timeline; the Production bar stays at the bottom, so that you can generate again from the **Review**.

The left panel is the summary of the workspace:

- **The four views**, one line each with its shortcut and its state: **Review** ("To review 2 · Running 1 · Final 3"), **Direction** (the length of the direction out of 4,000 characters and the number of conflicts), **Bible** ("Characters 2 · Places 1") and **References** ("6 in all · Global 4"). Click a line to open its view. The header of each view starts with the icon of the view, then its title and its counter; while the left panel is hidden, four icons take the place of that icon and switch between the views.
- **Engine**: the engine and the profile of the project, and the number of shots that set their own engine, with **Edit Engine** (chapter 8).
- **To check**: the conflicts between the direction and the shot prompts, each after the number of its shot (a click opens the **Direction** view with that shot as the sample shot); the cards that a shot prompt names without the shot casting them, and the characters that a shot casts without its prompt naming them (a click opens the card in the **Bible**); the shots whose latest take failed (a click opens the **Review** on that shot, chosen and brought on screen); and the seams to fix, each with **Match** (**See takes** when the point is not the color) and **Use the previous shot’s last frame** (chapter 12). With nothing to fix it reads "Nothing to check".
- Under it, the section of the assistant's continuity check, also titled **To check**, with "Assistant · 14:32" and a cross that dismisses it (chapter 10). The sparkles button of the header, **Ask the assistant to check continuity**, asks for that check.

**Review** lists the shots with their takes. The filters at the top, on one row, each with its count: **To review** (a shot that has a finished take that is not rejected and no final, or whose latest take failed), **Running**, **Final** and **All shots**; the view starts on **To review** when a shot is to review, on **All shots** otherwise. **Hide the rejected takes** shows when there are some. Each shot is a row: its number, name, stage, times, the part of the song it starts in (from the markers, see The band below), "Latest take failed" and **Prompt modified** when they apply, then its take cards (chapter 9), or "No take: Ctrl+G generates the chosen shot." Click the title of the row, or anywhere in the row outside its cards and buttons, to choose the shot: it gets a blue edge on the left. Click a take card, or its thumbnail, to choose the take: it opens in the viewer, the card lights up and its shot is chosen. In **All shots**, a line between two shots that do not match names the seam ("Seam 02 → 03") and its issues, with **Match**, **Use the previous shot’s last frame** and **Compare end and start**, which opens the band of the Storyboard on that seam; a click on the line chooses the seam. Previewing a take or comparing two opens the viewer above the rows, and adjusting the color of a shot opens it too. Once open, it stays: **Back to the sequence**, or Esc, goes back to the cut on the chosen shot; the cross **Close the monitor**, or a second Esc, closes it. At the bottom, "3 shots with a final out of 5" and **Assemble chosen takes (3)**. On the right, in place of the Inspector, the panel of the Review is about what you chose in the view, and sets no shot:

- **a take**: **Since this take** when the instruction of the shot changed after it, with the words of today’s instruction that its prompt did not carry in green; **Prompt sent**, the text the engine received; **Compare**, **With final** or **With another take**; its seams with the previous and the next shot, measured only for the placed take, and what a next shot that starts from its end would get;
- **a failed take**: what happened, what was asked, and **What to do**: **Retry take C**, then depending on the cause **Open Edit Engine** and **Shorten 05 in the Storyboard** (GPU memory full), **Edit the instruction of 05…** (refused text) or **See 04 in the Review** (a take that started from the previous shot);
- **a shot**: the progress of its takes, where a finished take is chosen with a click, and the composed prompt that its next take will send;
- **a seam**: the end and the start side by side, **Compare in the monitor** (the two placed takes, when both shots have one) and **Compare end and start**, the gaps with their actions, **Start from the end of the previous shot** and **Color of 03**, which grades the arriving shot;
- **nothing**: the state of the Review, **Next to review**, which chooses that take and brings its row, and the shortcuts.

Each panel ends with the shot read only (instruction, cast, engine) and **Open in the Storyboard**, where the shot is set. The labels **Reject**, **Candidate** and **Final** stay on the cards; the duration, the source in, the fades, the sound, the **Flag** **Favorite** / **Rejected**, cut, duplicate, delete and the **Takes** tab are not in this panel. Esc first closes the viewer, then drops the choice. A sound, a marker, a title, a shot prompt, a frame, a track or a reference chosen elsewhere stays chosen there, and the panel shows its empty state with a line that says so (“The audio clip “theme.wav”, selected in Media, stays selected there.”).

**Direction** shows the five fields of the global direction in large, each with its hint, its counter and **Library & assistant**; the header gives the length of the whole direction out of 4,000 characters, a text added to the prompt of every shot. When shot prompts contradict the direction, an alert lists the conflicts ("2 instructions contradict the direction"), each with a link such as "06 · See in the composed prompt", which makes its shot the sample shot of the right panel ("06 · In the composed prompt" once done); the Review, opened next, brings the row of that shot on screen. While the **Characters and identity** field is empty, a line takes its place and points to the Bible, with **Open the Bible** and **Add a free text**; once filled, it stays a free text added to every shot, with **Turn into a card** (see The bible below). On the right, in place of the Inspector, **Composed prompt**: choose a **Sample shot** and read the prompt that shot would send to the engine of the project with the direction as it stands (**Prompt sent to the engine**, with its warnings). It follows what you type. The sample shot follows the chosen shot, in the Review, in the Storyboard or through the link of a conflict; with no shot chosen, it is the first shot that has an instruction. Choosing it in the picker of the panel pins it, and **Follow the chosen shot** frees it; a line under the picker says which of the three applies. When it comes from a conflict, the panel recalls the conflict and highlights the two sentences that contradict each other in the composed prompt, or shows them as they are when no engine composes the prompt. **Edit the instruction of 06…** opens the instruction of the sample shot. While the project has no shot, the panel reads "No shot": "Create shots in the Storyboard to see the composed prompt."

**References** shows the board of references: the families as pills (**All**, **Identity**, **Sets**, **Motion**, **Sound**), each with its count, a search field, **Reference**, which adds one, and two groups, **Project** and **Shots**. Each card shows the tags of its reference, the same as in the Bible, the shot editor and the Inspector: its type with its icon, its role when it says more than the type, its scope (**Project** or **Shot 02**) and the cards of the bible it belongs to. The badge **Not sent with this engine** shows when the engine of the project ignores the references (chapter 8). The four families are **Images and identity**, **Sets**, **Motion guides** and **Sound**. A reference is global (it goes with every generation) or applies to one shot only: select it and set its **Scope** in the panel on the right, **Project** or **One shot**: with **One shot**, choose the shot in the list that appears, by its number; nothing changes before. A new project has no reference: the board says so, and **Reference** adds the first one. A **Sound** reference is a voice, a music or an ambience: select it, click the pencil and choose its type and its sound (a sound of the project, **Library** or **From computer**); the panel says what the engine of each shot does with it (chapter 13, Sound that goes with the generation). Its card shows the length of the sound and a player.

The panel on the right of **References** answers "what does the engine really get". With a reference chosen: its **Scope**, its **Card** (the character or place it is linked to, or "Voice of Lina"), and **What each shot gets**, one line per engine and profile of the shots with what they get: "the picture", "the sound, as a guide", "mixed onto the take", "not the picture", "past the limit (9)", "no readable media", or "left out" by the shots that exclude it, and "card not cast" for the shots that do not cast the card it is linked to. Under it, the shots its card's text goes into, whatever the engine, and the shots whose own words, written in the shot editor, replace that part or, written for another engine, are not sent. **Goes into N shots** lists the shots as chips: a chip opens the Review on that shot. **Start image from this reference** opens the shot editor on its start images (for a project reference, choose the shot first), **Preview** shows the media, the pencil edits its name, type, media and role, and **Remove the reference** deletes it. With a shot chosen in the Review or the Storyboard, the panel shows **References of shot 05**: what its engine gets, the project references with **Sent** or **Left out** for this shot (a picture of a card the shot does not cast is struck through, "card not cast"), the pictures it gets from its cast cards that are attached to other shots (**From the cast cards**), its own references and **Add a reference to 05**, and the board highlights the references that go with the shot. With nothing chosen, it gives the counts and what each engine of the project gets. Only the Ref2VA profile of MiniMax H3 sends the references themselves; the other engines get the text of the cast cards, and the engines that lay audio mix the sounds onto the take.

#### The bible

The **Bible** view holds one card per recurring character and one per place, the characters first. A card shows its identity images (the references linked to it), its visual tag, its type (**Character** or **Place**), its text, its props, "Cast in 3 shots" with the numbers of those shots (click one to open its takes in the **Review**, on that shot chosen and brought on screen), and two warnings: "Named but not cast: 09", with **Cast**, which casts the card in those shots, and "Cast but not named: 08". **Add a character** and **Add a place**, in the header, add a card. Under the cards, **Cast shot by shot** is a grid of the shots and the cards: a click casts a card in a shot or takes it out, and a shot has at most one place, so casting another place replaces it. A cell framed in dashed orange that reads "named" is a shot whose prompt names the card without casting it; a check framed in orange is a character cast but not named.

Click a card to edit it on the right, in place of the Inspector: its **Visual tag**, short and concrete ("the red-haired woman in the navy raincoat"), **Face and costume**, one fixed paragraph, and **Props** for a character, **Description** for a place, then **Identity images** and **Delete the card**, which also takes it out of the shots that cast it. While no card is chosen, that panel reads "No card chosen": "Choose a card of the Bible to edit it here." Under **Identity images**, tick references of the project, **Images and identity** for a character, **Sets** for a place, or click **Add an image** and pick an image of the project, from the **Library** or **From computer**: the page makes it a global reference of that family, linked to the card. The link is optional, and only MiniMax H3 in Ref2VA uses it, describing a linked reference sent with a shot with the words of the card. At the bottom, **What each engine gets** says how many shots the text of the card goes into, whatever the engine, and, engine by engine, whether its images and its voice go.

Under **Voice**, a character card holds what its lines need: **Voice description** ("a low, husky voice, slow pace"), given at the first line of the character in each shot; **Spoken language**, or **Project language**, which the **Spoken** menu of the Bible view header sets for the whole project (English by default); and **Voice reference**, a sound of the references (Sound family) that MiniMax H3 in Ref2VA takes as the voice of the character when the shot sends it. A voice reference is never mixed onto a take. Deleting a character keeps its lines, said by an unnamed voice.

You can also cast cards in a shot in the **Cast** section of the shot editor or of the Inspector: tick its characters and pick its place. The cards are then repeated word for word in the prompt of that shot, in the format of its engine: as subject definitions at the head of the prompt with MiniMax H3, after the action in a single paragraph with LTX, before the action with Wan and the cloud models. Write the visual tag of each character you cast in the shot prompt, the same way ("The red-haired woman in the navy raincoat opens the door."): the shot editor, the Inspector and the estimate warn when it is missing, and the estimate also warns when a Wan prompt goes past the 512 tokens Wan reads. A card without a visual tag enters no prompt. Text alone does not hold a face: a consistent first frame or the references of Ref2VA remain the surest way.

The **Characters and identity** field of the global direction works as before: its text is added to every shot. While it is filled, the **Direction** view offers **Turn into a card**: the text becomes a character card cast in every shot, with its first words as visual tag (check it), and the field is emptied. **Edit › Undo** brings it back.

### Mix

The left panel is **Sounds**, with a music note and, once the project has some, the number of sounds ("4 sounds"), and in its header the two import buttons (chapter 6). It holds the sounds of the project (drag one to a track, or use its plus button to add it at the playhead), then the **Roles** (**Dialogue**, **Music**, **Ambience**, **SFX**) with their number of tracks. The mixing console takes the place of the timeline. Its header holds the role filters (**All**, **Dialogue**, **Music**, **Ambience**, **SFX**), each with its number of tracks, **Audio track** and the same two import buttons. It starts with the strip **V1 · Shots**, the sound of the videos on V1, with its meter, **M** and **S**; then come the audio tracks with their faders, **M** and **S**, pan, equalizer, compressor, filter, reverb and delay sends, and meters. The center is the viewer. The four tracks of a new project are empty, and until you import a sound the **Sounds** panel says "No sounds in this project." and "Import music, voices or ambiences.", with **Library** and **From computer**, which open the audio import (chapter 6). The console plays the audio files you import (chapter 13).

### Play

The cut of V1 played in a large viewer, with the timeline under it. Play has no side panel, no Inspector and no Production bar: the viewer takes the whole width with its transport bar (monitor volume, go to the start, previous and next frame, play, loop, the timecode, framing guides, aspect ratio, resolution and full screen), and shows next to the volume the shot under the playhead ("Shot 2/6 · Harbour"). You hear the same mix as in the other workspaces: the sound of the V1 shots and the audio tracks, with their mute, solo, faders and effects.

- **Timeline.** The one of the other workspaces, with its toolbar, its rows (**Titles**, **Prompts**, **Frames**, **V1 · Video** and the audio tracks) and its ruler. Click or drag on the ruler to move the playhead; select and edit as elsewhere. **Fit** shows the whole cut. Drag the thin line above the timeline to give it more or less height: Play shares that height with Media, and with Mix when it shows the timeline.
- **Loop.** With **Loop** on, playback starts again from the beginning at the end of the cut, or from the In point at the end of the range when there is one. This is the same in every workspace.
- **Keyboard.** Space plays and pauses, the arrows move by one frame (1 s with Shift), Home goes to the start and End to the end. The other shortcuts of the timeline work as in the other workspaces.
- A shot with no media yet shows its name and prompt. A preview of a take or of a source media stays in the workspace where you opened it: Play always shows the cut. The side panel and Inspector buttons of the project bar are greyed out; the panels come back in the other workspaces, where the Inspector shows what you selected in Play.

## 5. Projects

Your projects are saved on the PotionUI server, in your account, as you work. There is no file to keep and nothing to export to avoid losing them. The page lists only your own projects.

### Opening the page

The page opens the project you used last. If it no longer exists, it opens your most recently modified project. If you have none (your first visit, or you deleted them all), it creates the starter project (chapter 1) and opens it.

**Projects made with an earlier version** lose their 3D scenes, their 3D shots and their Control videos when they open. The reference video of each 3D shot first becomes a **Motion guides** reference of the shot it guided, of type Control video: with the Ref2VA profile, MiniMax H3 carries its motion over to the shot (chapter 8). A frame captured in a 3D scene stays in its shot as an ordinary image.

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

If you open the same project in two tabs, windows or devices, or the assistant changes it while you edit (chapter 10), the page that saves second started from an out-of-date version, and the server refuses its save. That page then reads the saved version and merges it with its own: what changed on one side only is kept, and when both sides changed the same thing (the same name, the same length), the page keeps yours. The shots stay end to end, each prompt and frame in its shot, and the lists of a shot (its characters, the references it leaves out) keep what each side added and drop what either removed. A shot deleted on the other side goes, even if you had edited it, with its prompt and its frames: the page says so, and Ctrl+Z brings it back with your edit. It says "Changes saved elsewhere were merged into the project", or how many of your edits it kept over the other ones, and Ctrl+Z undoes the merge. **File › Version history…** brings back an earlier state if you need it. In the rare case where the page has nothing to compare with, it loads the saved version and shows "Project reloaded: it changed elsewhere": the changes you had not saved in this page are then lost.

### When the project was deleted elsewhere

If you delete the project from another tab or device while it is open here, the next save is refused because the project no longer exists. The page stops saving it, shows "This project was deleted elsewhere", then opens your most recently modified project, or creates the starter project if you have none. If that fails, the page shows "Could not open Video Producer" with a **Retry** button. The changes you had not saved are lost.

### Undo and redo

**Edit › Undo** and **Redo** (Ctrl+Z; Ctrl+Shift+Z or Ctrl+Y) work on the changes you made in the page, up to 100 steps. The history is kept in the page, not in the project: loading the page again, opening another project, creating a project, restoring a version and a reload after a conflict all empty it. An undo is a change like any other, and it is saved too. Dragging a slider counts as one step, and so does one press of an arrow key (or Home, End, Page Up, Page Down); Ctrl+Z and Ctrl+Y work even while a slider, a checkbox or a switch still has the focus. In a text field, they stay the browser's.

## 6. Media

The media of a project are the images, videos and audio files you imported, and the takes of the project (chapter 9). The **Media** workspace lists them (chapter 4).

### Importing

Media come from two places: your PotionUI library and gallery, or the computer your browser runs on. Each place has its button: **Library** (a folder) and **From computer** (an arrow going up). They are the same two icons, side by side, in the header of the Media panel, of the **Sounds** panel of the **Mix** workspace and of the console; their tooltips read "Import from the PotionUI library" and "Import files from this computer", with Ctrl+I and Ctrl+Alt+I in the Media panel. An empty Media panel and an empty **Sounds** panel show them with their names. The **Import** menu of the project bar offers both.

- **Images and videos from the library.** **File › Import from the library…** (Ctrl+I) and the **Library** buttons open the window **Import images and videos**. It is the PotionUI picker of your library: the files you uploaded to PotionUI and the generations you copied there.
- **From the gallery.** **File › From the PotionUI gallery** opens **Import from the gallery**, with your past generations. Every file of a generation can be picked on its own. Only images and videos can be picked.
- **Audio from the library.** **Audio › Import audio from the library…** and the **Library** buttons of the **Sounds** panel and of the console open **Import audio files**, the picker of your library with audio only.
- **From this computer.** **File › Import from this computer…** (Ctrl+Alt+I) and the **From computer** buttons open the file window of your system, where you can pick several images, videos and audio files at once. **Audio › Import audio from this computer…** and the **From computer** buttons of the **Sounds** panel and of the console offer audio files only; another kind of file is refused there ("… cannot be imported here: only audio files are accepted.").
- **By dropping files.** Drag files from your computer onto the Media panel: a frame shows while you hover it, red with "Only images, videos and audio files can be imported" when what you drag is not accepted. Or drop them on the timeline: they are placed at the time where you drop them, which a line and "Drop at" with the time show. Images and videos go on the video track **V1**, as new shots one after the other, or on **Frames**; audio files go on an audio track. A track that does not take what you drag is framed in red ("Not accepted on this track"), and dropping there tells you where each kind goes.

The files you can bring from the computer are those PotionUI accepts: images `.jpg`, `.jpeg`, `.png`, `.gif`, `.webp` and `.bmp`, videos `.mp4`, `.webm`, `.mov`, `.mkv` and `.avi`, audio `.wav`, `.mp3`, `.ogg`, `.flac`, `.m4a` and `.aac`. A file of another kind is refused before anything is sent, for example "“notes.pdf” cannot be imported: only images, videos and audio files are accepted."

The files from the computer are sent to your PotionUI library one at a time. The **Imports** panel, at the bottom right, lists them with a bar and a percentage each, "Waiting" for those not started yet and a button to cancel each one; a file reads "Imported" once it is in the project, and the panel closes by itself. Each file becomes an item of your library: you find it in the **Library** pickers of every project and in the PotionUI library. A file whose content is already in your library is not stored twice, and a file already in the project is counted apart, as with the pickers. The largest file and the room you have are those of your PotionUI storage plan: when a file cannot be stored, the page says so with the reason, for example "“Rushes.mov” could not be imported: the file is too large for the server." Captures, in the dark and light themes of the English interface: files dragged over the Media panel in `docs/screenshots/media-import-local.png`, the **Imports** panel while they are sent in `docs/screenshots/upload-progress.png`, and a file dragged over the timeline in `docs/screenshots/timeline-drop.png`.

In each picker you tick several files and confirm them together. The files then appear in the Media panel and the page shows, for example, "2 files imported". A media that is already in the project (same origin) is not imported again: the page counts it apart, for example "2 files imported · 1 file already in the project", or "1 file already in the project" when nothing is new. When some cannot be imported it adds, for example, "1 file could not be imported": the file is no longer available, or its kind is not accepted by the window. If your server has no picker, the page says "The media picker is not available on this server."

An import from the library or the gallery copies nothing: the project keeps a reference to the library item or the gallery file, and the address the page uses to show it. A file from the computer is copied once, into your library, and the project keeps a reference to that item. If you delete the file from PotionUI, the project can no longer show or play it.

### In the Media panel

After the import, your browser reads the duration and the size of each file. The duration shows at the bottom right of the thumbnail. For the selected item the panel shows **Duration**, **Format**, **Collection** and **Origin**: **Gallery** or **Library** (a file from the computer is in your library, so it reads **Library**); the thumbnail carries the same word. The frame rate of an imported video comes from the library when the library knows it, and shows after the size (for example "1280×720 · 25 fps"); otherwise, and for a gallery file, **Format** shows the size only. The collection pills sort images under **Images**, videos under **Videos** and audio files under **Audio**, and each pill gives the number of media it holds. **Generated** holds the videos of the finished takes of the project (chapter 9). A capture of the panel after an import is in `docs/screenshots/media-import.png`.

### Removing a media

The trash icon of a thumbnail (it shows when you hover or focus the thumbnail) or of the details at the bottom of the panel removes the media from the project, after a confirmation that says where it is still used: the shots that play it go back to "To generate", the audio clips and the start, end and reference frames that place it are removed, and the references keep their place without an image. The file stays in your PotionUI library. **Undo** in the message, or Ctrl+Z, brings everything back.

The video of a take you removed stays removed: it does not come back when the project opens again or the page reloads, and the take is neither put back on its shot nor made **Final** again. The take stays in the list of its shot (chapter 9). To put it back, click **Final** on its card, **Use this take** in the viewer, or **Assemble chosen takes**. The takes that finish afterwards arrive as usual.

### Thumbnails

An image is its own thumbnail. For a video, the page uses the thumbnail that PotionUI made for it when there is one, and otherwise a frame that your browser captures from the file. Thumbnails are not saved in the project: they are made again when the project opens. They show wherever a media or a shot shows its picture: the Media panel, the Inspector, the timeline and the viewer.

### Playback

- **Video and images.** Put the media in the cut (**Add to cut**, or drag it to the timeline). The viewer then plays the real video in step with the playhead, or shows the image, with the fades and the color settings of the shot. To look at a media on its own, double-click it or click **Preview**: the viewer shows it, a video with the controls of your browser and an audio file with an audio player, and **Back to the sequence** brings you back.
- **Sound of a video.** The viewer plays the sound of each shot's video with its picture, at its place in the sequence, with the fades of the shot. It goes through the console: the strip **V1 · Shots** shows its level, and the master fader and the monitor volume of the viewer act on it. Mute it for one shot (the speaker of the shot on the timeline, or **Shot sound** in the Inspector), for every shot (**M** in the header of V1), or hear it alone (**S**) (chapter 13). A take generated without a sound track stays silent, as it does in the export. Your browser reads the sound from the file a second time, next to the picture, from a second and a half before the shot starts.
- **Audio.** An audio file placed on a track plays through its strip of the console. The faders, mute and solo, pan, equalizer, compressor, filter and sends act on the real sound, the meters show it, and the clip draws the waveform of the file in the timeline (chapter 13).

The takes of the real generation are ordinary videos and play like any other video (chapter 9). When the file of a shot's media is no longer reachable (you deleted it from your library or gallery), the viewer shows **Media offline** ("The source file of “…” is no longer available: import it again or choose a take.") and so does the thumbnail of the shot on the timeline.

## 7. Inspector

The Inspector follows the selection and its header tells what is selected: **Audio clip**, **Title**, **Shot prompt**, **Reference frame**, **Marker**, **Reference** or **Console strip**. For a shot, the header holds three tabs in place of the title, left of the close button: **Shot**, **Takes** with the number of takes, and **Color**. Under them, the shot starts with a thumbnail, the name (click it to rename the shot), the stage and the times. The three tabs:

- **Shot.** **Edit shot…**, which opens the shot editor (chapter 4), with the number of drafts of the shot beside it; on a shot at the Draft stage, **Make take A final** with the engine it will use ("On" followed by the engine); **Duration and source** (the duration, where the shot starts in its source and the length of the source), **Frames** (the **First frame** and the **Last frame** of the shot, and the button **Use the previous shot’s last frame**; chapter 12), **Fades** (**In** and **Out**), for a video **Shot sound** (**Mute this shot**, with a line that says whether the shot is heard and why not), the **Cast** of the shot from the bible (chapter 4, The bible), its **Dialogue** (its lines, with **Edit the dialogue…**, which opens the shot editor), the **Flag** (**None**, **Favorite** or **Rejected**) and three icons to split the shot in the middle, duplicate it and delete it.
- **Takes.** The take cards of the shot, grouped by label (**Final**, **Candidates**, **Drafts**, **Rejected**), the switch **Hide the rejected takes** when there are some, and **Drafts of this shot** with its number of drafts (chapters 8 and 9). The tab does not generate: the Production bar does.
- **Color.** The luminance scope, the match with the previous shot, presets and fine settings (chapter 12).

The other items have their own panel:

- **Audio clip:** its track, start, duration, gain, its **Reference for the generation** switch, fades, the **Slices** section (chapter 13), and a button that opens its strip in the console.
- **Title:** the text, the subtitle, the start and the duration.
- **Shot prompt:** the text, the **Library & assistant** link, the **Editor** button, the warnings about the direction, the start, the duration, the influence, and the global direction that applies.
- **Reference frame:** the image (picked among the images of the project, which a new project does not have), the position, the role (start, end, transition, identity, style) and the strength of its influence.
- **Marker:** the label and the position.
- **Reference:** the name, its tags, the type, the image, the role, the scope (**Project** or **One shot**) and the shot it applies to.
- **Console strip:** the name, the role, its **Reference for the generation** switch, **Slice on the shots** for all its clips (chapter 13), the effects (**Equalizer**, **Compressor**, **Filter**), the sends and **Delete track A2** (with the number of audio clips that go with it; chapter 13).

With nothing selected, it shows the project (format, H3 profile, content), a reminder of the main shortcuts and a **Project properties…** button. With several shots picked (chapter 4, Picking several shots), its header says **Selection** and it sums up the picked shots: their number, their length, their stages, their list and **Clear the selection**.

In Director AI, the **Review** view puts the panel of the chosen take, shot or seam in its place, the **Direction** view **Composed prompt**, the **Bible** view the card you chose and the **References** view the chosen reference or shot with what each engine gets of it (chapter 4): another selection stays chosen in its workspace, and a line at the bottom of the panel says so. The Inspector itself does not appear in Director AI.

## 8. Production bar and generation

The Production bar sits at the bottom of **Storyboard** and **Director AI**. It reads like a sentence: a target (**Shot**, **Range** or **Sequence**, or **3 shots** when shots are picked), the range with the number of shots and prompts it holds, a quality (**Draft** or **Final**), the number of drafts of the target shots, then the engine of the project: the **Generation engine**, its **Profile**, the **Margin** of the reference tracks when a sound can guide the generation, the number of shots that set their own engine, and **Edit Engine** (the sliders); then the queue button (the list), the estimate and **Generate selection**. When the window is too narrow for all of them, what does not fit goes into **More engine settings** (the dots), at the end of the engine settings. A number with a warning icon after the counters is the number of direction conflicts in the range; click it to see them. Generation is real: a take is a video made in the background by the engine you pick. In Director AI, the **Shot** target aims at the shot that the view shows (the chosen shot in **Review** and **References**, the sample shot in **Direction**, none in **Bible**), never at the playhead, and the bar names it by its number ("Shot 06") instead of the times; with no shot it reads "No shot chosen" and Ctrl+G generates nothing.

### Choose the engine

- The **Generation engine** pop-up lists what your admin enabled and assigned to you, in groups named after the backends. A group named after your admin's own backend holds the video presets that run on their hardware, for example **Wan 2.1 / 2.2**, **MiniMax H3** or, on a 12 GB card, **MiniMax H3 (12 GB)**. Each cloud provider has its own group, with its video models by name. Your choice is saved with the project. Whether a preset runs on this machine or on a studio server is decided by PotionUI, and the take card tells you afterwards. Hover the pop-up to see the group and, for a preset that runs on the admin's hardware, the free memory of its GPU ("16.0 / 24.0 GB free"). In a narrow window the pop-up moves into **More engine settings** (the dots). A capture of the pop-up and of the bar around it, in the dark and light themes of the English interface, is in `docs/screenshots/engine-popup.png`.
- With no engine, the pop-up reads "No engine" and the bar says "No generation engine: an administrator must enable a video preset or a cloud model." An admin also sees the link "Open plugin settings". When the engine of a project is no longer available, the pop-up reads "Engine no longer available" and the bar says "The engine of this project is no longer available: pick another one." A project from an earlier version that named a placeholder engine is moved to the matching real engine when you open it.
- **Quality.** **Draft** makes quick takes at the resolution your admin chose, or the closest the engine offers; hover it to see which ("Quick draft in 832×480: check motion and framing"). **Final** makes takes at the largest resolution of the engine ("Final quality in 1280×720: keep it for the chosen takes"). To improve a draft you like, **Make final** (chapter 9) is usually the better way: it keeps the picture you chose. The quality you choose is saved with the project, and the bar takes it again when the project opens; a shot can set its own quality in its shot editor (chapter 4).
- **Profile.** FL2VA, Ref2VA or Hybrid AV: the bar shows only the profiles the engine can generate, and nothing when it can generate only one. Hover it to see what the profile does.
- **Margin** (0 to 10 seconds, 0 by default) widens the part of a reference track that guides MiniMax H3 before and after each shot (chapter 13). It shows only when a sound can guide the generation: MiniMax H3 with Ref2VA, for the project or for a shot.
- A shot can set its own engine, profile, quality and seed in its shot editor (chapter 4); the bar then counts these shots ("1 own engine"), and these settings come before the project's.
- **Edit Engine** opens a window with all the options of the engine, as its preset defines them on the Generate page: the speed, the steps, the sampler, the guidance, the models, the LoRAs, the enhancements and so on, grouped by the tabs and sections of the preset. A value you set shows its default under it and a button to go back to it; the options that a speed profile sets (8 steps for Distilled) follow it until you change them. The window leaves out what Video Producer sets itself: the resolution follows Draft or Final, the frame rate follows the preset, and the prompts and references come from the project. The menu at the top shows the options of another engine without changing the engine of the project, and the options of each engine are kept: you find them again when you come back to it. The **Project** section holds the **Drafts per shot**, 1 to 8: how many takes, A, B and so on, a shot gets when it has no number of its own (see Drafts per shot below). **Save** keeps the options with the project; they go into the generation of every shot that runs on that engine, and the estimate counts the steps you asked for ("8 steps instead of 24: each take is counted at about 0.33× the time"). An option that no longer fits its engine (after an update of the preset, for example) is left out and the bar says so. The window also opens from **Production › Edit Engine…** and from **Edit Engine** on the **Engine** line of Director AI.

### Read the estimate

The estimate sits on the right of the bar once an engine is picked: a short line with the time, the memory (a cloud model has none) and, on a window 1280 pixels wide or more, the minutes of quota or, for admins, the cost. Hover it for the detail. It follows your changes half a second after you stop, once the project is saved: until then it reads "The estimate updates once the project is saved." and, while it computes, "Estimating…". The detail has these lines:

- **Scope.** The shots, the number of takes they make together and the resolution: "2 shots · 5 takes in 832×480".
- **Time.** "Time ≈ 4 min on MiniMax H3 (measured on 3 takes)". It comes from the takes already made with the same preset, engine and resolution, whose real durations were measured: that is the calibration. With none yet it reads "Time: — (no measure yet on MiniMax H3)" and the bar shows "—". It fills in after a few generations, and a measure only serves the backend that made the takes.
- **Memory.** "Memory ≈ 22.5 GB, 16.0 GB free on Local Generation". It is an estimate from the size of the model files, never a guarantee. "Memory: unknown" when it could not be estimated.
- **Quota.** Your monthly Video Producer GPU minutes: "Quota: 5 min needed, 40 of 60 min left this month", "Quota: exempt" if you are exempt, and "Cloud: no GPU quota used" for a cloud model, which does not use them. It shows as **GPU quota** in the status bar when your admin set a limit. When your minutes are limited, the minutes of a take are reserved when it is created and adjusted to its real duration when it ends; a take that fails or is cancelled gives them back. With no limit, or if you are exempt, no minute is reserved or adjusted. Until a preset has been measured, each second of video counts for 10 seconds of GPU.
- **Cost.** Admins only, for a cloud model: "Cost ≈ $0.84", or "Cost: unknown for this model" when the provider publishes no price.

### Blocks and warnings

What blocks **Generate selection** (the button is disabled and the bar shows the first reason; hover it to see them all):

- no valid range;
- neither a global direction nor a shot prompt in the range;
- an empty shot prompt in the range;
- no engine, or an engine that is no longer available;
- a preset that is missing or no longer assigned to you ("This preset is missing or no longer assigned to you.");
- a profile the engine cannot generate ("Wan 2.1 / 2.2 cannot generate the Ref2VA profile: switch to FL2VA or to MiniMax H3.");
- model files your admin has not installed ("Models to install for this preset: …"): ask your admin;
- a cloud engine without a model ("Pick a cloud model for this engine.");
- a Ref2VA shot with no reference that can be sent ("“Shot 2” has no reference: Ref2VA needs at least one for this shot.");
- a spent quota ("GPU quota exceeded: 5 min needed, 2 min left this month."): switch to a cheaper quality, a shorter range or a cloud model;
- a Ref2VA shot that would send only sound ("“Shot 2”: Ref2VA needs a picture or a video next to the sound of the shot."): MiniMax H3 needs a picture or a video to anchor a soundtrack;
- a shot that sends a reference track or mixes sound onto its take on a server without ffmpeg ("ffmpeg is not available on this server: the sound of the shots cannot be cut."): ask your admin.

The buttons that start takes outside the bar (**Retry** and **Make final** on a take card, **Generate their drafts** and **Generate new drafts** in the **Synopsis and breakdown** window) do not wait for the estimate, but your admin's server applies the same rules and the page shows the first reason in a message.

What only warns, without blocking:

- a memory estimate above what the GPU has: "Will stream through host RAM, slower." The weights pass through the server's memory. The generation goes on, more slowly, and fails if the server lacks the memory for it (chapter 17);
- the FL2VA profile with no frame linked to a shot: "“Shot 2” has no linked frame: it will be generated from text only." The generation goes on from the text, and the card of the take says "text only". When the shot has a previous shot with a finished take, an icon next to the warning in the Production bar, **Use the previous shot’s last frame**, gives it a first frame (chapter 12);
- an engine that generates from text only, such as the (8 GB) Wan presets, for a shot with linked frames: "This engine generates from text only: the frames linked to “Shot 2” will not be used." The generation goes on from the text;
- a shot longer than the engine allows: "“Shot 2” is longer than this engine allows: it will be cut to 15 s.";
- a shot whose sound is mixed onto the take: "“Shot 2”: its sound will be mixed onto the take, not used as a guide." (chapter 13);
- a shot whose sound the engine ignores: "“Shot 2”: its sound is ignored by this engine.";
- a reference track that sends nothing: "“Shot 2”: the reference track A2 · Music is muted, nothing of it is sent.", "… has no sound under the shot, nothing of it is sent." or, with MiniMax H3 in Ref2VA, "… is silent under the shot, nothing of it is sent."

Three notes appear only in the estimate tooltip: "Memory use could not be estimated.", "No time measured yet for this engine and resolution." and, with MiniMax H3 in Ref2VA, "“Shot 2”: its sound guides the generation." When something blocks the generation, the tooltip lists the warnings under the blocks. A capture of the tooltip, with a shot whose sound is mixed onto the take and a reference track silent under it, is in `docs/screenshots/estimate-sound.png`.

If the sound of a shot cannot be read or stored when you click **Generate selection**, no take is created and a message names the shot ("“Shot 2”: a sound it sends can no longer be read." or "… its sound could not be cut or stored.").

### Generate

**Generate selection** (Ctrl+G) saves the project and starts, for each shot, as many takes as its number of drafts, each with its own seed (or the seed of the shot, chapter 4). Each shot uses the engine, profile and quality it sets in its shot editor, and those of the project and of the bar otherwise, so a range can mix engines. A shot is built from its shot prompt followed by the filled fields of the global direction, and from its frames and references, according to the profile (see below). If the project could not be saved, nothing starts ("The project could not be saved: generation not started.").

- **Drafts per shot.** Each shot has its own number of drafts, from 1 to 8: the drafts field of its Storyboard card (for a shot to generate), the quick edit of the band, beside **Edit shot…** and under **Drafts of this shot** in the Inspector, and in the shot editor. A shot that never got a number uses the number of the project (**Drafts per shot** of the Edit Engine window, 2 by default). The field of the Production bar shows the number of the target shots and sets it for all of them; when they differ it reads **Mixed**. The page sends the number of each shot with the request, so a range can mix shots of 1 and of 4 drafts.
- To generate one shot, select it, with the target **Shot**, then click **Generate selection**: the Storyboard cards, the quick edit of the band, the Inspector and the viewer have no Generate button.
- **The target of Ctrl+G.** The shots picked with Ctrl+click or Shift+click when there are at least two (chapter 4, Picking several shots): the target of the bar becomes **3 shots**. Otherwise the target of the bar: with **Shot**, the selected shot, or the shot under the playhead; with **Range**, the shots of the range (without the **Source** shots when there are others); with **Sequence**, every shot.
- **Queueing while takes are running.** Ctrl+G, and the button, which becomes **Add to queue** meanwhile, add the generation of the target to the queue: they are no longer refused. The bar keeps the progress and **Cancel**, which stops everything. A message says how many shots were added ("3 shots added to the queue") with **Undo**, which takes out of the queue the takes this Ctrl+G just made, and only them. Two Ctrl+G in a row go out one after the other, in the order you pressed them.
- **A shot that already has a take queued or running** gets one more, with the next letter (B after A): nothing is replaced or cancelled, and the message says so ("3 shots added to the queue, 1 of them as one more variant"). **Undo** takes the addition back when it was one too many.
- **The chain stays consistent.** A shot that starts from the end of the previous one (chapter 12), added while the take of the previous shot is still queued or running, waits for that take (the one with the same letter, else the first one), as in a single batch: it does not start from an old frame.
- Your admin limits how many generations you can have in progress at once. The takes past that number wait as **Queued** and start by themselves, in the order of the queue, as the others end (see The queue below).

### Follow the takes

- Each take shows its state: **Queued**, **Generating** (with the step and the percentage), **Failed**, **Cancelled**, or, once finished, its duration. The bar shows the step and the progress of the whole batch, the Storyboard card and the block of the shot on the timeline show the step, the percentage and a bar for their shot (the mean of its takes in progress), and **Window › Background tasks** counts the takes in progress ("2 takes in progress").
- When a batch ends, a message tells how many takes are ready ("2 draft takes ready") with a **View** button that opens the **Review** view of Director AI, and another how many failed ("1 take failed"). PotionUI also sends the notifications "Video Producer: take ready" and "Video Producer: take failed", so you can leave the page: the generations go on without it, and the takes are there when you come back.
- **Cancel** on a card stops that take. **Cancel** in the bar, or **Production › Cancel the generation**, stops all the takes in progress ("Generation cancelled"; "No generation running." if there are none). The GPU minutes they reserved are given back.
- **Retry** on a failed card starts a new take for the same shot, with the same seed, quality and engine. The failed take stays in the list.
- **The queue.** The list button of the Production bar, **Production › Generation queue** (Ctrl+Alt+G) and the count of takes in the status bar open the generation queue, a list under the button of the bar; from **Media**, **Mix** or **Play**, the page first switches to Director AI. It lists your takes waiting or in progress in the order they run: first the ones handed to the engine ("Handed to the engine", or the step and the percentage of a take that is generating), then the waiting ones, numbered ("Waiting · no. 2"). Each line gives the shot, the variant, the quality, the label and the engine, with two buttons: **Move to the head of the queue** (the arrow, for a waiting take that is not first: it becomes the next one) and **Cancel**. The top says how many takes run out of how many may run at once ("1 / 2 running"), and a line counts your takes waiting for other projects: all your projects share one queue. Click the name of a shot to select it. A take that waits for the end of the take of the previous shot (chapter 12) says "Waiting for take A of “Shot 2”" and cannot move to the head. A capture is in `docs/screenshots/generation-queue.png`.

### Profiles per preset

The **Profile** of the Production bar, also shown on the **Engine** line of Director AI, says what guides the generation. What an engine can do depends on its preset, and the page greys the profiles it cannot run.

| Profile | Wan 2.1 / 2.2 and its (8 GB) presets, LTX-2 / 2.3, LTX-2.5, cloud models | MiniMax H3 | MiniMax H3 Fast and VDN, MiniMax H3 (12 GB), MiniMax H3 Fast (12 GB) |
|---|---|---|---|
| FL2VA | Yes | Yes | Yes |
| Ref2VA | Greyed | Yes | Greyed |
| Hybrid AV | Greyed | Yes | Yes |

- A greyed profile carries a badge such as "Ref2VA · Hybrid AV: MiniMax H3 only", with the explanation "Wan 2.1 / 2.2 cannot generate Ref2VA, Hybrid AV: reference images (Ref2VA) and generated sound (Hybrid AV) need MiniMax H3." In the **References** view, the badge **Not sent with this engine** tells you that the engine ignores the references ("References are sent only with the Ref2VA profile on MiniMax H3; Wan 2.1 / 2.2 ignores them.").
- **FL2VA** uses the frames linked to the shot: a start and an end frame give a take "first and last frames", a start frame alone "first frame", and no frame "text only", with the warning above. Chapter 12 shows how to take the first frame from the previous shot.
- **Ref2VA** sends the references of the shot, then the pictures of the cards it casts, then the global ones, to MiniMax H3: up to 9 images, 3 videos and 3 audio files. The cast chooses the pictures: a picture linked to a card goes to every shot that casts the card, even when it is attached to another shot, and a project picture linked to a card goes only to the shots that cast it. A video of the **Motion guides** family is the source of the motion of the shot: MiniMax H3 carries its motion over to the subjects of the shot.
- **Hybrid AV** works like FL2VA on MiniMax H3, whose model makes the picture and the sound together.
- A shot can use another profile than the project in its shot editor (chapter 4).

What the engine you picked cannot do is not an error: it has a plain gray badge, as these profiles, **Upscaler not available** (chapter 9) and **Not sent with this engine** on the references of an engine without Ref2VA.

### The settings of earlier versions

The **Advanced workshop** of earlier versions is gone, with its settings that the engine did not use. What acted is now in the Production bar and the **Edit Engine** window (engine, profile, quality, drafts per shot), summed up on the **Engine** line of Director AI, and in the shot editor (engine, profile, quality and seed of one shot). The removed settings were: consistency between windows, lock character identity, motion guide first, the generation windows with their length and overlap, the final resolution, the seed, the steps, the guidance (CFG), the LoRAs, the track that drives the performance, lip sync, follow the rhythm of the cut, audio / picture offset, result naming, post-processing, insert variant A automatically, and the Hybrid builder weights with their saved profiles. A project made before keeps their values, which nothing reads; a preset only exposes the controls it declares, and MiniMax H3, for example, has no guidance and no negative prompt. The seed of a take is drawn by the server and shown on its card, unless the shot sets its own, and the resolutions follow the draft and final rules of chapter 8.

## 9. Takes and final

A take is one generated video for one shot. Its video is an ordinary PotionUI generation: it stays in your generation history (the gallery), even if you delete the take here.

- Drafts are made at the resolution your admin chose (832×480 unless changed) or the closest the engine offers. The frame rate of a take is set by the preset (Wan 16 fps, MiniMax H3 24 fps). The timeline and the exports use the frame rate of the project.
- Several variants are made per shot: A, B, and so on. A new generation for the same shot goes on with the next free letters (C, D…), separately for drafts and finals; **Retry** and **Make final** keep the letter of the take they come from. They are listed in the Inspector, tab **Takes** (grouped by label), and in the **Review** view of Director AI, one row per shot (chapter 4). Both lists have the switch **Hide the rejected takes** when the takes include rejected ones.

### The take card

- The thumbnail carries the letter of the take. Click it to preview the take in the viewer ("Preview take A"); **Back to the sequence** brings you back.
- The first line gives the quality, "Draft quality", "Final quality" or "Final quality · upscale", so that it does not read like the **Final** label, then the label of the take (**Draft**, **Candidate**, **Final** or **Rejected**), then the state ("Queued", "Generating", "Failed", "Cancelled") or, once finished, the duration. The next lines give the profile and how the shot started ("FL2VA · first and last frames", "FL2VA · text only", "FL2VA · first frame", "Ref2VA · references"), the resolution and, for a final, the take it comes from ("from A"), the seed ("Seed 123456") and the engine that made it (the preset or the model, then the backend). **Prompt modified** shows under the first line when the shot was edited after the take was made.
- A queued take shows only its state ("Queued") above an empty line; a take that is generating shows the step, the percentage and a progress bar. When it fails, it explains in your language the usual causes, for example "The server’s GPU ran out of memory: try a lower resolution or fewer frames." (28 known causes are explained); for any other cause it shows the reason that PotionUI gives (in English) or, when it gives none, "The generation failed (invalid_request)." with the code.
- **Compare** puts the take beside a second one in the viewer, both playing in a loop ("Pick a second take to compare"). **Extract a frame at the playhead** (the image button of a finished take) saves one image of the take as a first or last frame of the shot (chapter 12). **Generation details** opens PotionUI's window about the generation. **Delete** asks "Delete this take?" ("Take A of “Shot 2” leaves the list. The video stays in your generation history.").
- A capture of take cards, in the dark and light themes of the English interface, is in `docs/screenshots/takes-cards.png`.
- On a take in progress, **Cancel** stops it. On a failed one, **Retry** starts a new take.
- Under a take that is not in progress, **Reject**, **Candidate** and **Final** set its label (see Labels).

### Labels

Every take has one label:

- **Draft**: what a new take is.
- **Candidate**: a take worth keeping. A take made by **Make final** starts as a candidate.
- **Rejected**: a take you do not want. **Hide the rejected takes** takes them out of the lists without deleting them.
- **Final**: the take the shot plays. Only one take of a shot is final.

**Final** puts the take on the shot: it plays on the timeline, the shot becomes Draft or Final (its quality), and the thumbnail of the card shows a check mark. The take that was final becomes a candidate. The first draft that finishes for a shot that was still "To generate" is put there for you, and so is a finished final, so they become **Final** by themselves. A take whose video you removed from the project (chapter 6) is not put back for you: it stays in the list, and **Final** puts it back on its shot. **Reject** and **Candidate** are greyed on the final take ("The final take stays final until another take of the shot becomes final"); click **Final** on another take first. Click **Reject** or **Candidate** again to make the take a draft again. **Edit › Undo** and **Redo** keep the label in step with the timeline: the take the shot plays after the undo becomes **Final** again, and a shot that plays no take keeps no final. In the viewer, a take previewed outside the cut has **Use this take**, which makes it final too. **Assemble chosen takes** (at the bottom of the **Review** view) puts all the final takes in the cut; without any it says "First choose takes for the shots." The export warns about a shot whose take is rejected.

Projects made before the labels keep their marks: a chosen take is **Final**, a take kept with the star is **Candidate**, a take flagged with the thumb down is **Rejected**, the others are drafts. A capture of the labels in the Inspector, in the dark and light themes of the English interface, is in `docs/screenshots/take-labels.png`; the Storyboard cards and the timeline block of a shot in progress are in `docs/screenshots/storyboard-takes.png` and `docs/screenshots/timeline-progress.png`.

### Make final

**Make final** on a draft card (also the button of a Storyboard card, **Make take A final** in the Inspector, **Shot › Make take final** and Ctrl+Shift+G) opens the window "Make final · Shot 2 · A" with the line "Draft in 832×480 · seed 123456". It offers two ways, and a third when your administrator has set up the guided render:

- **Upscale** is the default. The engine enlarges the take as it is: the picture and the motion do not change, and it is the fastest way. Wan, LTX, MiniMax H3 Fast and VDN, MiniMax H3 (12 GB) and MiniMax H3 Fast (12 GB), and cloud takes go through SeedVR2 ("SeedVR2 enlarges this take as it is: fastest, the motion does not change."); a take of the base MiniMax H3 preset uses the upscale mode of its own preset ("MiniMax H3 enlarges this take with its own upscale mode: the motion does not change."). Pick the **Target resolution**: 720p, 1080p, 1440p or 4K (the window starts on the resolution of your project), then click "Upscale to 1080p".
- **Re-render at full resolution** generates the shot again at the largest resolution of the engine, with the same seed: "slower, the result may differ slightly."
- **Guided render** renders the shot again with LTX-2.5 at its largest size (1280×720 in 16:9), following this take: "same motion and framing, new detail." It starts from the first frame of the shot, or of the take when the shot has none or was edited since, and lays the sound of the take on the new one. It is experimental: slower than an upscale, and the look can drift from the take. The button only shows when LTX-2.5 and its Layout-To-Render IC-LoRA are installed and assigned to you.

When no upscaler is assigned to you, the window shows the badge **Upscaler not available** and the explanation "Upscaling this take needs SeedVR2: ask an administrator to install it, or render the take again at full resolution." (the **Make final** button of that take card shows the same sentence as its tooltip), the resolutions are greyed and only the re-render is offered. A take of the base MiniMax H3 preset does not need SeedVR2, as long as its preset is assigned to you. An upscale takes time: on a 12 GB graphics card, the upscale of a 5-second Wan draft to 1080p took about two and a half hours. A capture of this window, in the dark and light themes of the English interface, is in `docs/screenshots/make-final.png`.

The new take is a **Final** one ("Final quality", "Final quality · upscale" or "Final quality · guided" on its card) that says which draft it comes from ("from A"). You get "Upscale to 1080p started", "Render at 1280×720 started" or "Guided render at 1280×720 started", the final appears on the card list when it ends, and it is put on the shot ("Final version ready and applied to the shot"). A final uses GPU minutes like any take and is checked against your quota.

### Make the film final

Once each shot of the Storyboard has its **Final** take, make the whole film final in one go: **Production › Make the film final…**, or **Final film** in the header of the Storyboard (band and grid), at the bottom of the **Review** view of Director AI, and on the **Move to final** card of **Synopsis and breakdown › To produce**. The button gives the shots at final quality out of the generated shots ("Final film 3/8"), a spinner while final takes run, and a check once the whole film is final.

The window "Make the film final" works like **Make final**, for every shot at once. Each shot starts from its Final take, which serves as the reference: its motion and framing are kept. Choose once:

- the **Method**: **Upscale** (the default), **Guided render** or **Render again**, each with its explanation and what becomes of the sound ("Sound: the sound of each take is kept.");
- for an upscale, the **Target resolution** and, when the film has takes of the base MiniMax H3 preset, the **Upscaler**: **Automatic** (that preset upscales its own takes, SeedVR2 the others) or **SeedVR2 for all**.

The project keeps your choice for the next time. Then the window lists the shots with their state:

- **To make final**: its Final take is a draft;
- **Already final**: it is skipped, unless you turn on **Redo the shots already final (N)**, which makes them final again from their draft (they then read **To redo**);
- **Generating** with its percentage, or **Queued**: a final of the shot is already on its way, and it is skipped;
- **No Final take**: the shot has no finished take labelled Final yet. The window names these shots ("2 shots have no Final take yet (04, 07): they stay as they are in the film.") and its button becomes **Go without the missing shots (N)**, so that the film never goes final incomplete without saying so;
- **Imported source**: a shot made of an imported video is always skipped.

Each row also shows the take it starts from ("Take A · 832×480"), **Prompt modified** when the shot was edited after it, and "Last final failed" or "Last final cancelled" when its last final failed or was cancelled. Under the list, the estimate of the whole pass: the time when it was measured, the memory, the GPU minutes against your quota, and the reasons that block it, each with its shots. **Make N shots final** starts every final at once ("Final pass started: 8 takes"); they wait in the queue like any take, and the Production bar shows their progress. Open the window again to follow them: "3 final takes in progress" with a progress bar, and **Cancel the pass (3)**, which stops the final takes still queued or running ("Final pass cancelled: 3 takes stopped"). Each finished final goes on its shot and becomes **Final**, and the draft stays in the takes of the shot, as a **Candidate**.

## 10. Assistant

The assistant is the PotionUI chat, working in its own mode for this page, **Video Producer assistant**. It reads your project and can drive the whole page with its thirteen tools, the actions it can run: read the project in detail; add, change, reorder and delete shots; write their prompts and fix the contradictions with the global direction; cut your synopsis into shots; cast the shots from the bible and give them frames and references; check the continuity; generate takes, follow them, label them, assemble the edit and export the video.

Two kinds of change:

- **What costs or cannot be taken back waits for you.** Writing over a shot prompt, deleting shots, generating takes and proposing a cut of the synopsis show an approval card with a preview, and nothing happens in your project until you click **Approve**.
- **The rest is done at once.** Adding and changing shots, labelling a take, assembling and exporting are saved as soon as the assistant runs them, the page shows them as they happen, and Ctrl+Z (or **Undo** on the message "Project updated by the assistant") takes each one back.

### Before you start

- Your admin has to configure a language model in PotionUI (Admin › LLM / Assistant) and assign it to you. It must be able to call tools, and a local model server set up for the assistant (llama.cpp `llama-server` or Ollama, with the settings of the administration guide) or an online provider such as OpenAI is the safer choice: the model built into PotionUI ran out of memory, or was too small to call the tools, on a 12 GB graphics card in our tests. Without a model the chat says that it is unavailable (see "If it does not work" below).
- The assistant works on your project as saved on the server. The page saves your edits when you send a message, so the assistant sees what you see, and its changes come back to the page and are merged with what you type meanwhile (see What it changes, and what it does not).
- Keep the Video Producer page open while you chat: the assistant only knows your project while the page is open on it.

### Open the assistant

Click **Assistant** in the project bar, choose **Window › PotionUI assistant**, or press Ctrl+J (⌘J on a Mac). The chat opens over the page. On a new conversation, the mode chip in its header reads **Video Producer assistant**. A conversation keeps its mode for good ("Mode is fixed after the conversation starts"): if the chat shows a conversation started elsewhere in PotionUI, its header says "Started in …" and offers **start a new chat**.

### What the assistant sees

With each message, the page sends the assistant a summary of your project:

- the project: its name, its saved version and its prompt language;
- where you are: the workspace, the playhead (and the shot under it), your selection and the range;
- the synopsis and the global direction: the five fields and the H3 profile;
- the bible: the visual tag and the words of each card;
- the shots in timeline order: number, name, start and end, stage, how many takes it has and which one is final, whether it has a first and a last frame, the beginning of its shot prompt and the visual tags it casts;
- the conflicts that the page flags between a shot prompt and the direction, and the color and look matches it measured between neighbor shots;
- the state of the production: target, quality, progress, queue and the engine of the Production bar.

The summary is text and it is kept short: 40 shots at most, 800 characters of the synopsis, 240 of each field of the direction and 160 of each shot prompt, so a longer text is cut in what the assistant reads. It holds none of your images, videos, references or audio, and the assistant sees no picture. When it needs more, the assistant reads the project itself (the tool **Read project**): the full prompts, the takes of each shot with their letter and label, the references, and the names of your media, which it can use as frames and references. If you leave the Video Producer page, the summary stops: the assistant says the page is not open and asks you to open a project.

### Requests to try

You write to the assistant in your own language. The examples below are only examples; select a shot first and the assistant knows which one you mean. You can name a shot by its name or by its number in the timeline ("shot 3").

#### Request 1: write the prompt of a shot

For example: "Write the prompt of the shot “The gulls”: a low angle on the water, backlit."

1. The chat shows a card **Write shot prompt**, marked **Needs approval**, showing the prompt now and the new text (only the new text when the shot has no prompt yet).
2. Click **Approve**. The new text becomes the shot prompt of that shot (the prompt is created when the shot had none). The page updates at once and says "Prompt of “The gulls” updated by the assistant"; the card turns to **Applied**.
3. Click **Reject**, with a reason if you like, to leave everything as it was.

#### Request 2: fix the contradictions with the direction

When the **Direction** view of Director AI lists conflicts (for example "The global direction excludes neon lights." for a prompt that asks for neon), ask: "Fix the conflicts between my direction and my shot prompts."

1. The card **Fix conflicts** shows one block per shot to rewrite, with the old text and the new text.
2. **Approve** applies all the rewrites in one change, and the page says "2 prompts rewritten by the assistant". **Reject** applies none: it is all or nothing.

#### Request 3: cut the synopsis into shots

For example: "Cut my synopsis into shots of about 5 seconds." You can also tell a story in the chat and ask for the cut.

1. The card **Split synopsis** lists the proposed shots, each with its time range and "name: beginning of its prompt". It proposes 1 to 24 shots of 2 to 15 seconds, with names of 34 characters at most.
2. **Approve** does not change your project yet. The page opens the **Storyboard** and says "3 shots proposed in Storyboard". The **Proposed breakdown** list (the same one as **Propose a breakdown**) shows the shots: untick the ones you do not want (**Keep shot 1**), rename them, then click **Add 3 shots at the end**. The shots join the end of your film as shots "To generate", each with its shot prompt, and the page says "3 shots added to the storyboard".
3. **Close the proposal** drops it. A new proposal replaces the previous one.

#### Request 4: check the continuity

For example: "Check the continuity between my shots and tell me what to fix." The sparkles button of the left panel of Director AI, **Ask the assistant to check continuity**, types this request for you. This one only reads your project, so there is no card.

1. When the assistant has answered, the page says "2 continuity points to check" (or "Continuity checked: nothing to fix"), with a **Show** button when the left panel of Director AI is not on screen.
2. In the left panel of **Director AI**, under the page's own list, a **To check** section, with "Assistant · 14:32" beside its title (the time of the check), lists the pairs of neighbor shots to look at, as "Shot 1 → Shot 2". Click a pair to open the shot in the **Review**. Under each pair, a line says what is wrong and a second line how to fix it.
3. What it looks for: a shot without a prompt; a shot prompt that contradicts the global direction; a shot shorter than 2 s or longer than 15 s; a shot with the FL2VA profile and no first frame; a shot prompt that does not name a character the shot casts from the bible; a camera move that changes between two shots; a jump of brightness or color temperature (the page measures these on the images, the seam frames of the shots when they have some and their thumbnails otherwise, and the line carries the badge **Measured**; chapter 12); and a point on the look of two takes at a seam, which the server measures on their images with SigLIP (chapter 12), so its line carries the badge **Measured** too. Shots that come from a source are skipped.
4. **Dismiss the check** (the cross of the section) removes the list. Ask again to refresh it.

#### Request 5: add, change and order shots

For example: "Add two shots after “The gulls”: a close-up on Mara’s hands, 3 s, and a wide shot of the dock, 5 s, with Mara in the dock." Or: "Make shot 2 last 6 seconds, move “Exit” to the start and cast Mara in it."

1. The chat shows the tool it runs (**Add shots**, **Update shots**). No card: the change is saved at once and the shots appear on the page while the assistant is still answering. The page says "Project updated by the assistant", with **Undo**.
2. A new shot comes "To generate", with its prompt. Changing the length of a shot moves its prompt, its frames and the shots after it, like the shot editor; a take that becomes too short leaves the shot, which goes back to "To generate".
3. The assistant can also give a shot a first or last frame and attach references, from the media of your project ("Use the image “Gate” as the first frame of shot 3"), set the number of takes per run, and turn on or off the start from the previous shot's last image.
4. Ctrl+Z takes the change back, and the page saves the shot as it was. To change the prompt of an existing shot, the assistant uses request 1, with its card.

#### Request 6: delete shots

For example: "Delete the shots “Exit” and “Credits”." The card **Delete shots** lists them with their time range and the beginning of their prompt. **Approve** deletes them with their prompts, frames and own references, and the later shots move up; their takes stay in the project. Ctrl+Z brings them back. **Approve** deletes the shots the card shows, even if they moved meanwhile. If these shots change between the card and **Approve** (moved, renamed, another length), the card says it is out of date and its button reads **Approve anyway**; if a shot of the card was deleted meanwhile, nothing is deleted and the assistant shows a new card. A card you rejected never runs: if you ask again, **Approve** runs the new card, the one on screen.

#### Request 7: generate and follow the takes

For example: "Generate a draft of shots 1 to 3." The assistant uses the engine of the Production bar and the number of takes of each shot, unless you give one ("two takes each").

1. The card **Generate takes** shows the shots, the number of takes, the quality, the engine, the GPU minutes they need and what is left of your monthly minutes, and the estimated time. Nothing starts before you click **Approve**, and **Approve** starts what the card shows: the same shots, quality and number of takes, even if you changed them meanwhile. If a shot of the card was deleted, or the estimate made again costs more than the card said, nothing starts and the assistant shows a new card.
2. When a take cannot start (a model to install, minutes used up, a profile the engine cannot make), the assistant says why and shows no card.
3. After **Approve**, the page says "3 takes started by the assistant", with **Show**, and the Production bar shows the progress, as for a generation you start. Ask "Where are my takes?" and the assistant reads the queue: the takes running or waiting, their place, the minutes left and the latest exports.

#### Request 8: choose the final takes

For example: "Make take B of “The gulls” the final one." (The letter is the one on the take card.) A final take is put on its shot in the edit, like **Use this take**, and the previous final of the shot becomes a candidate. The assistant can also label a take **Rejected** or **Candidate**. Ctrl+Z takes the final take off the shot. A final take stays final until you or the assistant make another take of the shot final.

#### Request 9: assemble and export

For example: "Put the final takes in the edit and export the video for the web." The assistant puts every final take on its shot, as **Assemble chosen takes** does, tells you which shots have no final take yet, then starts the export (web, or social in 9:16; the resolution of the project unless you ask for another). The page says "Export started by the assistant", with **Show**, which opens the export window: download the video there when it is ready. The export runs on the processor of the server, not on the graphics card.

### Suggestions that fill the request for you

Three places of the page start the chat with a request already typed. You can read it, edit it, then press Enter: nothing is sent for you.

- **Ask the assistant to check continuity** (the sparkles button of the left panel of Director AI): "Check the continuity between my shots and tell me what to fix."
- **Ask the PotionUI assistant**, in the **Prompt library & assistant** window. The window closes first. The request depends on what the window was writing into: "Help me write the prompt of the shot “The gulls”.", "Help me write the prompt at 5.0 s.", "Help me write the “…” field of the global direction." or, with no target, "Help me write a prompt for this project."

If you had already typed something in the box of the chat, your text stays and the suggestion is not added. If your PotionUI is too old to fill the box, the chat just opens with an empty box and you type the request yourself. The suggestions are written in the language of the interface.

### What it changes, and what it does not

- It writes shot prompts (requests 1 and 2), proposes shots (request 3), adds, changes, orders and deletes shots (requests 5 and 6), generates takes (request 7), labels them (request 8), assembles and exports (request 9). It does not edit the synopsis, the global direction, the bible cards, the titles, the color, the sound or the mix, nor choose the engine, nor make the final pass of the film, nor import media: ask it and it answers in text, and you do it on the page.
- **Propose a breakdown** and **Production › Split synopsis into shots…** are not the assistant: they only cut the synopsis into sentences, one shot per sentence. **Production › Continuity check** opens Director AI on the **Review** view with its left panel, where **To check** lists what the page found, and does not call the assistant.
- Each change of the assistant is a new version of your project: **File › Version history…** shows it with the word "Assistant". On the page, **Edit › Undo** (Ctrl+Z) takes it back like your own changes, one tool call at a time.
- If you edit the project while the assistant works, both changes are kept. When you and the assistant changed the same thing (the same name, the same length), your version wins, and the message says so: "Project updated by the assistant; 1 of your edits was kept over its change".
- A generation, a label in the takes and an export are not in the project: Ctrl+Z does not cancel them. Cancel a take in the queue, and delete an export in the export window.
- The assistant writes shot prompts in the prompt language of the project (chapter 15) and answers you in your language. It never translates what you wrote. The contradiction checks only read texts in the prompt language.
- The list **To check** and the proposal appear once, when the answer arrives. They disappear when you leave the page or open another project, and reopening an old conversation does not bring them back: ask again.

### If it does not work

The chat itself is a PotionUI window: its buttons (**Tools**, **New chat**, **Approve**, **Reject**, **Retry**) keep PotionUI's labels.

- **"Chat is currently unavailable".** No language model is assigned to you. Ask your admin to add one in Admin › LLM / Assistant and assign it to you. (An admin reads "No enabled LLM configurations" instead.)
- **The assistant answers but never shows a card, or says it cannot act.** The **Tools** button of the chat box is off: hover it, it reads "Tools OFF"; click it to turn the tools on, and check that the tools of the group Video Producer are ticked in its list. Your admin may also have turned them off for the model, or the model may not be able to call tools: try another one.
- **The assistant does not seem to know your project, or the header says "Started in …".** The conversation was started in another mode. Click **start a new chat** from the Video Producer page.
- **The assistant says the page is not open on a project.** Open a project in Video Producer, keep the page open and ask again.
- **A card is Failed and quotes `version_conflict`, `project_not_found` or `shot_not_found`.** The project was saved from somewhere else at the very moment of the save, was deleted, or no longer has that shot. Let the page reload the project (**File › Open…**), then click **Retry** on the card or ask again. The assistant says so itself in the chat.
- **The assistant says `blocked` or that the takes cannot start.** The reason follows: models to install, monthly GPU minutes used up, a profile the engine cannot make, no engine in the Production bar. It is the same block as in the Production bar (chapter 8).
- **The assistant says several takes share a letter (`ambiguous_take`).** A shot has a draft and a final take with the same letter. Say which one ("the draft B"), or ask it to read the takes of the shot first.
- **With a small context window, the assistant first loads the production tools.** Under 24,576 tokens of context, PotionUI sends the tools that generate, follow, label, assemble and export only when the assistant asks for them: the chat shows a first call **use_tools**, then the real one. That is expected.
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
- **Composer.** Builds a prompt from four parts, **Camera movement**, **Lighting**, **Film style** and **Dialogue or acting intent**, for the H3 profile you pick (it starts from the profile of the project). Choose one option per part, or type your own in **Other…**, and fill in the subject, the action, the place and the emotion. The **Final prompt** stays editable, and **Recompose from the choices** brings it back. **Required references** tells whether the range has what the profile needs.
- **Insert** writes the text into the target: **Add to the text** adds it to the existing text, **Replace** replaces it.

The three H3 profiles and what each one asks for on the range:

| Profile | Meaning | It asks for | Engines |
|---|---|---|---|
| FL2VA | Continuity between the start and end images. | Start and end frames in the range. Without any frame, the shots are generated from text only. | All of them. |
| Ref2VA | Keep the identity of the references during the action. | An identity reference (character, object). The generation follows your references. | MiniMax H3 only (not its Fast and VDN variants, nor the (12 GB) presets). |
| Hybrid AV | The soundtrack, rhythm and dialogue drive the picture. | An existing audio track in the range (dialogue or music). | MiniMax H3, Fast and VDN, and the (12 GB) presets. |

The engine, not the table, has the last word: the page greys a profile the chosen engine cannot generate (chapter 8). The audio tracks of the project are not sent to the engine: MiniMax H3 makes the sound itself.

## 12. Color and continuity

Continuity is about the seams, the cut from one shot to the next. Video Producer measures the color of every seam, warns when two neighbor shots do not match, fixes the color in one click, and can start a shot from the exact image where the previous one ended.

### Color match

An alert appears only when two neighbor shots do not match: "“Shot” is brighter, darker, warmer or cooler than the previous shot". It shows in Director AI (under **To check** in the left panel, and on the seam lines of the **Review** in **All shots**), in the Storyboard (under **Continuity**, as an alert button on the card of the shot that opens the seam panel, and in the seam comparison of the band monitor) and in the Inspector. **Match** (**Match color** in the Storyboard) fixes it in one click by adjusting exposure and temperature to the previous shot. **Match colors (n)**, in the header of the grid and of the band of the Storyboard, matches each shot to the previous one at once, from the first seam to the last, each seam measured against the previous shot as already corrected; Ctrl+Z undoes it all. The **Color** tab also has the luminance scope, six presets (Original, Golden light, Cold morning, 35 mm film, Blue night, Soft) and fine settings (**Exposure**, **Contrast**, **Saturation**, **Temperature**), with **Reset** and **To all shots**. The seam view of the band has the preset, the fine settings and **Reset** for each of its two shots (chapter 4); it has no **To all shots**, which would also change the other side of the seam. Before a shot has an image, the tab says that color can be adjusted once the shot is generated.

**What the viewer shows.** Adjusting the color of a shot (a preset, a fine setting, **Reset**, **To all shots**, **Match**, **Auto match**, its **Strength** or **Remove**) brings that shot to the viewer, in every workspace: it becomes the selected shot, the playhead moves to its start when it was elsewhere, and a preview, a comparison or a seam that does not show it closes. The seam of the band shows both its shots: adjusting either keeps it open, without changing the chosen shot or the playhead. In the **Review**, the viewer opens if it was closed. Opening the preview of a take (Review, **Takes** tab, stack of the band) chooses its shot: that is the shot the Inspector shows and the one you adjust. The viewer shows the grade of a shot on the images of that shot: the cut under the playhead, the preview of the take placed on the shot (the one it plays), each placed take of a comparison, and both sides of a seam in the band, each with the grade of its own shot. A take that is not placed and a source media stay raw; a graded take says so next to its name ("shot grade"). With an **Auto match**, the preview of a placed take plays in a loop, without the browser's controls. The Storyboard grid and the Direction, Bible and References views of Director AI have no viewer: the playhead is already on the shot when you go to the band or to **Play**.

The measure is made on real images, for each shot that has one. The starter project has none yet, and the Storyboard then says "No match to check yet: the shots have no image." A resemblance percentage between two generated shots can also appear in the alerts ("Look to check between … and … (resemblance 56 %)"): it is measured by SigLIP on the images at the seam (see The look of the takes below).

### The look of the takes

The look of a take is measured by the server with SigLIP, the image model of the gallery search, and compared at each seam and with the bible. SigLIP compares the overall look of two images (costume, light, setting, the face as part of it): **it is not a face recognition**, so two people dressed and lit alike can pass, and the same character under another light can be flagged.

- **At a seam.** When two neighbor shots both play a take, the image the first ends on (at the end of its cut) is compared with the image the second starts on. Under 70 % the seam says "Look to check between “Shot 2” and “Shot 3” (resemblance 56 %)", in the seam panel of the Storyboard, the band monitor, the Review and To check, with **Compare the takes**, which opens the two takes side by side in the monitor of the band.
- **With the bible.** A take is compared with the pictures of each character card cast in its shot. The review panel of the take has a section **Resemblance to the bible** with each card and its score; under 60 % it says "drifts from the card", and To check lists "03: drifts from the card “Marin” (resemblance 54 %)" for a placed take. A card without a picture says so.
- **When it is measured.** Each take that finishes is measured in the background, a few seconds later, and never while a generation is running or waiting. Takes made before this version, and pictures added to a card later, are measured on demand: **Measure** in To check (with the number of looks not measured yet) or in the review panel of the take.
- **Without SigLIP on the server**, the looks say "SigLIP not installed" and nothing is measured; nothing is downloaded.

### Auto match

**Auto match**, in the **Color** tab of the Inspector, corrects the color of a take from an **Anchor** image rather than from the previous shot. The anchor offered is the start frame of the shot (its key frame), then another key frame of the shot, an image reference of the shot, the last frame of the previous shot and last a reference of the project: matching each shot to the previous one adds up drift, which the page recalls when you pick that anchor. The **Anchor** list stays editable; another anchor measures again.

1. The page measures, in CIELAB, the mean and the spread of the lightness and of both color axes on the anchor and on three images of the take (at 15, 50 and 85 % of the shot).
2. It derives a statistical transfer from them (Reinhard's method, in Lab), applies it at the chosen **Strength** (80 % by default) and shows the gap before and after, in ΔE, with the way the take drifts ("take warmer", "take darker"…). The **Anchor**, **Take** and **Matched** thumbnails let you compare.
3. On export, the match is baked into a 3D LUT (33³ points, a `.cube` file) that ffmpeg applies before the framing and before the fine adjustments. The viewer and the thumbnails show the same LUT (WebGL, or a computation on the page when WebGL is missing), not a CSS filter.

When the take of the shot changes, the match is no longer applied and the tab asks to **Measure again**. **Remove** deletes the match. **Reduce flicker on export** adds ffmpeg's `deflicker` filter to the shot; it only acts in the exported video.

### What the measure looks at

For each pair of neighbor shots the page compares the end of the first with the start of the second:

- for the previous shot, its **Last frame** image if it has one, otherwise its thumbnail;
- for the shot, its **First frame** image if it has one, otherwise its thumbnail.

Any image that you placed as a first or last frame counts, not only the images made in this chapter. The assistant's continuity check (chapter 10) marks the points that the page measured with the badge **Measured**; hover it to see what was measured: "Measured by this page on the seam frames: last image of the previous shot, first image of this one", or "Measured by this page on the shots’ thumbnails". The look of two takes at a seam carries **Measured** too, with "Measured by SigLIP on the images at the seam: the overall look, not a face recognition".

### Start a shot from the previous shot

A **seam frame** is an image taken from a take and set as the first or last frame of a shot. With the FL2VA profile a take starts on its first frame (chapter 8), so giving a shot the last image of the previous shot makes the two shots join without a jump.

**Use the previous shot’s last frame** is offered in six places:

- under each alert of Director AI, in **To check** of the left panel and on the seam lines of the **Review**, next to **Match** or **See takes**;
- under each alert of the Storyboard, section **Continuity**, next to **Match color**;
- in the seam panel of the Storyboard (the alert button of a grid card), in the seam comparison of the band monitor and in **To check** of the Synopsis and breakdown window;
- on the lines of the assistant's check that say that a shot has no first frame (chapter 10);
- in the **Frames** section of the Inspector, tab **Shot**, which shows the **First frame** and the **Last frame** of the shot ("None" when empty) and a button of the same name;
- as an icon next to the warning of the Production bar that says that the shot will be generated from text only (chapter 8).

When you click it:

1. The page saves the project and asks the server for the image at the end of the previous shot's cut: the last image that shot shows in your edit, at its in point plus its duration, from the take placed on it (its final or chosen take) or from its imported video. After a still, it is the still itself. The button reads "Extracting the image…" meanwhile.
2. The image is saved in your library as a PNG, added to the media of the project and set as the **First frame** of the shot, with full influence, at the start of the shot. You see it in the **Frames** row of the timeline and in the Inspector. The page says "Last image of “Shot 1” set as the first frame of “Shot 2”" with an **Undo** button.
3. Nothing is generated and the takes you already have do not change: the next take you generate for the shot starts from that frame. The frame only guides the generation; it is not drawn into an exported video.

If the shot already has a first frame, a window asks "Replace the first frame?" ("“Shot 2” already has a first frame. The new image replaces it; you can undo."). **Replace** swaps it and **Keep the current one** changes nothing. The replaced image stays in the media of the project. **Undo** in the message, or **Edit › Undo**, brings the previous frame back.

The action is greyed, with the explanation "“Shot 1” has no take or video yet.", while nothing is placed on the previous shot, and it is not offered for the first shot of the film.

### New shots start from the previous one

When you add a shot after another one (**Shot**, **New shot** and **Insert a shot after** in the Storyboard, the **New shot** command, or **Add N shots at the end** for a breakdown, yours or the assistant's), the new shot takes as its **First frame** the image at the end of the previous shot's cut, as if you had clicked **Use the previous shot’s last frame**. The page says "First frame of “Shot 3”: the last frame of “Shot 2”", with **Undo**. Splitting a shot at the playhead and duplicating a shot do not do it.

- **The previous shot has no take or video yet.** Nothing is set. As soon as a take arrives on it, the seam proposes the frame: "“Shot 2” now has an image: its last frame can open “Shot 3”", with **Use the previous shot’s last frame**, in Storyboard › **Continuity**, in Director AI › **To check** and on the card of the shot. This lasts while the new shot has no take of its own.
- **You keep control.** The frame is an ordinary first frame: change it or remove it in the shot editor (**First frame**) or in the Inspector.
- **The previous shot changes afterwards** (another take placed, another final, a trim of its in point or of its duration, the shots reordered): the first frame is never replaced behind your back. The seam says "The first frame of “Shot 3” is out of date: “Shot 2” changed after its last frame was taken" and its button becomes **Use the new last frame**, which takes the new image at once, without asking to replace. A first frame you chose yourself is never marked out of date.
- **To turn it off**, open **File › Project properties…** and switch off **Start each new shot from the previous one**. The option belongs to the project and is on in every project, including older ones. Off, new shots start without a first frame and the seam proposes nothing; first frames already taken still say when they are out of date.
- **An engine that generates from text only** (the Wan 12 GB and 8 GB presets in text-to-video) does not use first frames. The project properties say so under the option, and the estimate warns for each shot: "This engine generates from text only: the frames linked to “Shot 3” will not be used."

### Choose the chain before generating

Each shot but the first can start from the end of the previous shot: its first frame is then the last frame of the previous shot, and its take joins it without a jump. The project setting (**File › Project properties…**, **Start each new shot from the previous one**) stays the default; each shot can change it for itself, even before the previous shot has a take.

- **See it and set it.** A link chip follows the number of the shot, on its card in the grid and on its block in the band: sharp when the shot chains, a broken link and dimmed when it does not. A click switches it ("“Shot 3” starts from the end of “Shot 2”", with **Undo**); its tooltip says what will happen. An orange dot means an out-of-date frame or an engine that does not start from an image, a blue dot a take of the shot that is waiting. The switch **Start from the end of the previous shot** does the same in the seam panel (the alert button of a card), in the seam comparison of the band monitor, in the Inspector (tab **Shot**, section **Frames**) and in the quick edit of the band. Under the switch a line says what will happen: "The first frame is the last frame of “Shot 2”.", "The last frame of “Shot 2” is taken when the generation starts.", "A take of this shot waits for the take of “Shot 2”, then starts from its last frame.", "Waiting for take A of “Shot 2”", "The shot has a first frame of its own: it keeps it.", "The engine of this shot generates from text only: it does not use this frame." or "The shot starts from its text or from a first frame of its own.". A second line says "Follows the project" or "Set for this shot", with **Follow the project**. The shot editor does not carry the switch.
- **Turning a shot off** removes its first frame when it came from a previous shot (the image stays in the media); **turning it on** takes the last frame at once when the previous shot already has a take or a media. Ctrl+Z undoes either.
- **Generate in a batch.** Generate several shots at once (**Sequence** or a range in the Production bar): the shots chain in the order of the edit. The take of a chained shot waits, on the server, for the take of the previous shot to end, takes its last frame, then joins the queue. Meanwhile its card, the block of the shot on the timeline, the generation queue and the take card say "Waiting for take A of “Shot 2”" (**Waiting** on the block of the band), and it cannot move to the head of the queue. The wait goes on if you close or reload the page, and after a restart of the server.
- **Which take of the previous shot.** With several drafts, take A of a shot waits for take A of the previous shot, B for B; with no take of the same letter, it waits for the first one (A). When the previous shot is not in the batch but has a take in progress, the take waits for that one. When it already has a placed take or a video, the frame is the end of its cut, taken within seconds of the start; after a still, it is the image itself, at once.
- **Which frame.** The end of the cut of the previous shot as it will be once the take is placed on it: the duration of the shot from the start of the take, capped at the length of the take.
- **The frame arrives in the project.** Once taken, it becomes the **First frame** of the shot, as with **Use the previous shot’s last frame**: "First frame of “Shot 3” (take A): the last frame of “Shot 2”", with **Undo**. It never replaces a first frame chosen by hand, and within a batch the first frame that arrives stays (that of the take of the previous shot that finished first, which the page places on that shot when it was to generate). If the page was closed, the frame is set when it opens.
- **If the take of the previous shot fails or is cancelled**, the chained take fails too, with its reason ("The take of the previous shot this take was to start from failed. Retry it, then retry this one."), and its GPU minutes are given back. **Retry** starts it again: it waits for the new take of the previous shot, or takes the end of its cut when it has a placed take. **Cancel** in the bar cancels the whole batch, waiting takes included.
- **Estimate and quota.** The estimate counts the chained take as a take that starts from an image, and its GPU minutes are reserved when it is created. The time shown adds up the takes without counting the wait: chained takes run one after the other.
- **An engine that generates from text only** (the Wan 12 GB and 8 GB presets in text-to-video), the Ref2VA profile or a cloud model without a first frame make nothing wait: the take starts from its text.

### Extract a frame at the playhead

For another moment than the last image, use **Extract a frame at the playhead**, the image button on the card of a finished take (Inspector, tab **Takes**; Director AI, view **Review**). Its tooltip says "Saves the image of this take under the playhead as the first frame (first half of the shot) or the last frame (second half)". Put the playhead on the shot, at the moment you want, then click it:

- the image is taken from that take at the position of the playhead in the shot (for the take that the shot plays, its in point is taken into account);
- in the first half of the shot it becomes the **First frame**, in the second half the **Last frame**; a playhead outside the shot counts as its start or its end;
- the page says "Image at 2.5 s set as the first frame of “Shot 2”" (or "last frame"), and asks "Replace the last frame?" first when there is one.

### Other checks

The assistant can run more checks on request: shots without a prompt, contradictions with the global direction, durations outside 2 to 15 s, FL2VA shots without a first frame and camera moves that change between two shots, together with the color points above. Its answer is a second **To check** list in the left panel of Director AI (chapter 10).

## 13. Audio and subtitles

Audio lives in tracks, each with a role: Dialogue, Music, Ambience or SFX. **Audio › Add audio track**, **Audio › Import audio from the library…** and **Audio › Import audio from this computer…** bring sounds in; **Audio › Mixing console** shows the console. In the console each strip has a role, effects (**Equalizer**, **Compressor**, **Filter**; **+ effect** adds one), sends to the reverb and delay buses (R and D), pan, a fader (double-click it to go back to 0 dB), a meter, **M** and **S**; the auxiliary buses and the **Master** follow. The pills at the top, each with its number of tracks, show one role only. The titles of the timeline feed the subtitles (chapter 14).

### Tracks: add, delete

**Audio › Add audio track**, the **Add** menu of the timeline and **+ Audio track** in the console add an audio track at the bottom. Tracks are named **A1**, **A2**… by their place: delete A2 and the track that was A3 becomes A2. Their names (**Dialogue**, **Music**…) do not change.

To delete a track, select it (click its name on the timeline or its strip in the console) and click **Delete track A2** at the bottom of the Inspector, or press Delete; or right-click its name on the timeline and choose **Delete track…**. A window asks first and says what goes with it, for example "A2 · Music holds 3 audio clips. They are deleted with the track. Undo brings them back." **Delete track** deletes the track and its audio clips; **Edit › Undo** (Ctrl+Z) brings both back. The last track can be deleted too: an audio file you add afterwards gets a new track for its role. Captures, in the dark and light themes of the English interface: the track menu on the timeline in `docs/screenshots/timeline-tracks.png`, the confirmation in `docs/screenshots/lane-delete.png`.

### Mute and solo

**M** mutes a track, **S** solos it, on the timeline as in the console; the video track **V1** has them too, for the sound of the shots' videos. One rule decides what you hear, in the viewer as in the exported video:

- An audio clip is heard when its track is not muted and, if any track is soloed (V1 included), its track is soloed too.
- The sound of a shot is heard when neither V1 nor the shot is muted and, if any track is soloed, V1 is soloed too. **Mute this shot** (Inspector, **Shot sound**) or the speaker of the shot on the timeline mutes one shot.
- Mute wins over solo. Solo V1 and A1 to hear the shots with the dialogue only.

The Inspector of a shot says why its sound is not heard: "Track V1 is muted…" or "An audio track is soloed…". A capture of **Shot sound** with an audio track soloed is in `docs/screenshots/shot-sound.png`.

### Sound that goes with the generation

Two things send sound with the generation of a shot:

- **Sound references** (Director AI › References, family **Sound**; or **Add a sound** in the shot editor): a voice, a music or an ambience, global or for one shot, which a shot can exclude like any reference (chapter 4).
- **Reference tracks**: the audio tracks you check **Reference for the generation**, with the switch of the Inspector of the track or the **Ref.** button of its strip in the console. A small sparkles icon next to the track name on the timeline marks them. At each generation, the part of the track under the shot is cut on the server, its clips mixed with their gain, their fades and the volume of the track, silence where nothing plays, and sent with the shot. A shot can leave a track out with **Exclude** in its shot editor. A muted track, or one soloed away, sends nothing, and neither does a track with no clip under the shot: the estimate says so. With MiniMax H3 in Ref2VA, a track whose part under the shot is silent (its loudest moment at −60 dB or below) is not sent either, and the other sounds take its place.
- **Reference clips**: each audio clip has its own **Reference for the generation** switch in its Inspector. Left alone, the clip follows its track. Set, it wins over the track: a clip switched on is sent even from a track that is not a reference track, a clip switched off is never sent, even from a reference track. **Follow track A1** gives the choice back to the track. A sparkles icon before the name of a clip on the timeline marks each clip that is sent. Only the clips sent, under the shot, are cut, mixed, measured for silence and sent; a reference track whose clips under the shot are all switched off sends nothing and says nothing.

What the engine does with this sound depends on it, and the shot editor, the Storyboard card and the estimate say which:

| Engine | What happens | What the page says |
|---|---|---|
| MiniMax H3 with the Ref2VA profile | The sound is an audio reference: the generation follows it (at most 3 sounds per shot, shot references first, then those of the cast cards, then the reference tracks, then the global references; the same file is sent once). The part of each track is cut with the **Margin** of the Production bar before and after the shot. A sound cannot be the only reference: add a picture or a video. | "Guides the generation: MiniMax H3 follows this sound." |
| LTX-2, LTX-2.5, MiniMax H3 outside Ref2VA | The tracks and the sound references are mixed into one file exactly as long as the shot (no margin: the sound stays in sync with the picture) and laid onto the take. The picture is not made from it. | "Will be mixed onto the take, not used as a guide." |
| Wan, cloud models and the other engines | Nothing is sent. The tracks still play in your edit and in the exported video. | "Ignored by this engine: the sound stays in the edit only." |

The cut files are stored once per shot and per generation in your library, as WAV files named after the shot ("vp-sound-shot-01-a1.wav", "vp-sound-shot-01-mix.wav"; with MiniMax H3 in Ref2VA, the sound references are also stored again at the rate the model reads, "vp-sound-shot-01-sound1.wav"), so that every draft of the shot uses the same sound. A take made with a mixed sound plays it in the viewer like any take. Captures, in the dark and light themes of the English interface: the **Sound** references in `docs/screenshots/sound-references.png`, the shot editor in `docs/screenshots/shot-editor-sound.png`, the reference tracks in the console and the Inspector in `docs/screenshots/lane-reference.png`, the Storyboard cards in `docs/screenshots/sound-cards.png`.

### Slices of a sound

To choose which seconds of a long sound go with the generation, cut it into slices. Select an audio clip, set **Length** in the **Slices** section of its Inspector (5 s by default, from 1 to 60 s; the length is kept by the page for every clip until you reload it, and is not saved in the project) and click **Slice**, or use **Cut › Slice the clip into 5.0 s slices** (Ctrl+Shift+B). The clip becomes consecutive clips of that length on the same track, the last one shorter (or up to 0.1 s longer, so that no sliver is left over): each slice goes on from the same place in the file, with the same gain and the same **Reference for the generation** setting; there is no fade at the inner cuts, and the fades of the clip stay on its first and last slices. A clip makes at most 200 slices at a time. Each slice then has its own switch.

**Join** (or **Cut › Join the slices**, Ctrl+Alt+B) puts the slices of the selected clip back together: the clips of the same file on the same track that follow on from one another, on the timeline as in the file (within 0.025 s). Slices whose **Reference for the generation** setting or gain differs stay apart, so that a join never changes what you hear nor what goes with a generation: twelve slices of which the 3rd, 7th and 8th are switched off become five clips. A joined clip keeps the fade in of its first slice and the fade out of its last. **Edit › Undo** (Ctrl+Z) undoes a slicing or a join.

**Slice on the shots** (in the **Slices** section of an audio clip, or of an audio track for all its clips; also **Cut › Slice on the shots**) cuts at the edges of the shots of V1 instead of every N seconds: one slice per shot over the clip, each starting and ending exactly with its shot, with the same rules as above (same place in the file, gain, track and **Reference for the generation** setting, no fade at the inner cuts, the outer fades kept, at most 200 slices per clip). Two edges less than 0.1 s apart make one cut, at the later one: the rounding of the shot times (a few hundredths of a second between two shots) leaves no sliver, and a shot shorter than 0.1 s gets no slice of its own, its sound going with the slice of the shot before it. A gap between two shots, and the part of a clip that goes on past the last shot, become slices of their own, so that the switch of a shot's slice acts on that shot only and a shot added at the end later finds its slice ready. A clip that starts or ends less than 0.1 s from an edge is not cut there. **Edit › Undo** undoes the whole slicing, of a clip or of a track, in one step.

### Your audio files

The four tracks of a new project are empty. **Audio › Import audio from the library…** and **Audio › Import audio from this computer…** bring in your own audio files, and you can drop audio files on a track (chapter 6). The console plays them for real: the faders, mute and solo, pan, equalizer, compressor, filter and sends act on the sound you hear, the meters show it, and the clips of the timeline draw the waveform of the file.

## 14. Exports

**File › Export video…** (Ctrl+E) opens **Export and share**, with three tabs: **Video**, **To other software** and **Subtitles**. **File › Export to other software…** (Ctrl+Shift+E) and **File › Export subtitles…** open the other two. Before the export, the window warns about shots that are not final yet, shots that use a take you flagged **Reject** and direction conflicts that are not solved. Every export starts by saving the project; if that fails, the page says "The project could not be saved: nothing was exported." and exports nothing.

### Video

Pick a format and a resolution, then click **Export**.

- **Format.** **Web · H.264 MP4** has the aspect ratio of your project. **Social media · vertical H.264** is always 9:16: the shots fill the frame and are cropped around their center. **Master file · ProRes 422 HQ** is a MOV for editing and grading software: ProRes 422 HQ in 10 bits with 24-bit PCM sound. **Archive · H.265 10-bit** is a compact MP4 of high quality to keep: H.265 in 10 bits with AAC sound. The master and the archive have the aspect ratio of your project; they stay in the export folder and are not copied to your library (the window says "The master file and the archive stay in the export folder: download them from here.").
- **Resolution.** 720p, 1080p or 4K; the window starts on the resolution of your project. The short side of the picture is 720, 1080 or 2160 pixels. For a 16:9 project a web video is 1280×720, 1920×1080 or 3840×2160, and a social video is 720×1280, 1080×1920 or 2160×3840.
- **Whole sequence.** Every export renders the whole sequence; when you have drawn a range the window says "Exports render the whole sequence."
- **Audio stems by role (Dialogue, Music, Ambience, SFX) and the shots’ sound.** With this switch on, the export also writes five WAV files, 24-bit stereo at 48 kHz and as long as the video: one per role (the tracks of that role with their reverb and their delay) and one for the sound of the shots. Each is under the master fader and at the level the **Level** gave the mix, so that played together they make the sound of the video. You download a ZIP that holds the video and its five stems, named after the video (`Dawn_at_the_harbour_1080p_dialogue.wav`, and so on). A role you did not use gives a silent stem.
- **Sound.** **Level**: **As mixed** (the default), **Web and social · −14 LUFS** or **Broadcast EBU R128 · −23 LUFS**. The server first measures the mix (`loudnorm`, first pass), then applies one gain to the whole mix (second pass, linear mode): the dynamics do not change, and the gain stops before true peaks pass −1 dBTP, even if that leaves the mix a little under the target. **Crossfade between neighbouring clips**: **None**, 0.25 s, 0.5 s or 1 s. Two clips of one track that touch (within half a frame) fade into each other (`acrossfade`, equal power), centered on the cut and taken from the media past each side, without moving the second. Both settings are saved with the project. The window also says how many shots have a color match baked into a LUT, and which ones changed take since.

Under the choices the window shows the name of the file (the project name with spaces turned into underscores, then the resolution, for example `Dawn_at_the_harbour_1080p.mp4`, `Dawn_at_the_harbour_1080p.mov` for the master, `Dawn_at_the_harbour_1080p_archive.mp4` for the archive, and `Dawn_at_the_harbour_1080p_master_stems.zip` for a master with its stems, the format in the name), its frame rate and aspect ratio, "5 WAV stems in a ZIP with the video" when the stems are on, and the note "Rendered on the server with ffmpeg".

What the video holds:

- The shots in the order of the project, with their **Auto match** (3D LUT), the **Color** settings (exposure, contrast, saturation, temperature) and the fades of each shot. A shot with no file that the server can find, and every gap between shots, is black and silent. An image placed as a shot is held for the length of the shot.
- The sound of each shot's own video, with the fades of the shot, unless the shot or the track V1 is muted or another track is soloed, and your audio tracks as the console plays them: the gain and fades of each clip, mute and solo (the rule of chapter 13, the same as in the viewer), then the strip of each track (equalizer, compressor, filter, pan and fader), the sends to the reverb and the delay, and the master fader. What you hear in the console is what the file holds; only the fine timing of the compressor, and the last echoes of the delay, far below the mix, differ a little. A mono file plays on both sides at its full level, as in the console. The final level and the crossfades only apply when you pick them under **Sound**.
- Not in the video: the titles and markers, and the subtitles (always a separate file, see below).

If your admin has not installed ffmpeg on the server, the Video tab says "ffmpeg is missing on the server: video exports need it." (with a **Read the guide** link for an admin, and "Ask an administrator to install it." for anyone else) and **Export** is disabled.

### Follow the export

The export runs on the server, in the background. The window shows a card with the file name, its state (**Queued**, **Rendering**, **Ready**, **Failed** or **Cancelled**), the current step, a percentage and a progress bar:

| Step | What happens |
|---|---|
| Waiting in the queue | Another export is running on the server, which makes one at a time. |
| Assembling the shots | The shots are put end to end, with their color and fades. |
| Mixing the audio | The sound is mixed. This is the same run as the assembly: the step changes at 50 %. |
| Converting the video | The file of the format is made, then the stems when you asked for them. The percentage goes from 70 to 95 % during this step. |
| Saving the export | A web or social MP4 is copied into your library, and the stems are put in their ZIP with the video. |

- **Cancel** stops a queued or running export ("The export was cancelled."), at any step.
- You can close the window or leave the page: the export goes on. With the window closed the page keeps following it and shows a toast with **Download** when it is ready. PotionUI sends the notification "Video Producer: export ready" (or "Video Producer: export failed"), and when you open **Export and share** again the card is back.
- A project has one export at a time ("An export of this project is already running.").
- When it is ready the card says "Dawn_at_the_harbour_1080p.mp4 is ready" with its size, and offers **Download** and, when your PotionUI can show it, **Show in the library**, which opens your library on the videos. A web or social MP4 is also in your library like any video, so you can import it into a project (chapter 6); **Show in the library** is not offered for a master or an archive, which you download.
- A failed export says what failed ("ffmpeg could not assemble the video.", "The video could not be converted." or "The export could not be saved.") and, under it, the technical message of the server (chapter 17).

### Previous exports

Under the card, **Previous exports** lists the export in progress first, with its state, then the earlier exports of the project: format (followed by "stems" when they were asked for) and resolution, state, when it ended and its size, with a download icon (**Download <file>**) and a trash icon (**Delete <file>**). Deleting asks "Delete this export?" ("<file> is removed from the export folder. A copy saved in your library stays."): **Delete** or **Keep it**. With none, the list says "No video exported for this project yet."

The exported files are kept in your PotionUI storage, in a `video_producer/exports/` folder, until you delete them. Your admin sets a size budget for that folder, per user. When it is reached, your oldest finished exports are deleted to make room, and if that is not enough the export is refused: "The export folder is full: delete older exports and try again." The copy in your library does not count in this budget and stays when an export is deleted.

### To other software

Three files, built by the server from your saved project: **FCPXML** (`.fcpxml`), **OpenTimelineIO** (`.otio`) and **EDL CMX 3600** (`.edl`). Click a card, read its note and the beginning of the file, then click **Download** followed by the file name, which comes from the project name (for example "Download Dawn_at_the_harbour.fcpxml"). The page says "<file> downloaded".

- **FCPXML.** "V1 sequence with the chosen takes, shot names and in points." One video row, with a shot without media as a gap. No audio.
- **OpenTimelineIO.** "Video and audio tracks by role; opens in Resolve, Premiere (plugin) and Nuke Studio." The same video row, and one audio track per track of the console, named **A1**, **A2**… as on the timeline, with the position, role and gain of each clip. The audio clips carry no file.
- **EDL.** "Universal edit list (V1 only), for grading or conforming." One event per shot, with its name and its media file; a shot without media is on a black reel (BL).

These files carry the cut only: no fades, no color settings, no titles and no audio files.

**Media paths.** The files point to the real media files of your shots, as the server stores them: "Media paths are the real files on the server, taken from the saved project." The preview shown in the window lists file names, but the file you download holds the full paths on the server. If your editing software runs on another computer, those paths do not exist there: put the videos of your takes (download them from your gallery) and your imported media on that computer and relink them in your software.

**Importing.** Editing software that reads FCPXML 1.10 imports the `.fcpxml`: the project appears in an event named "Video Producer". The `.otio` file opens in the software named above and in other software that supports OpenTimelineIO. The `.edl` is read by editing and grading software that support the CMX 3600 format. Menus differ between software and between versions: follow the import command of yours.

### Subtitles

An SRT file built from the titles of the timeline (the title, then its subtitle on a second line), in time order. The tab lists the cues with their times ("No title to subtitle." when there is none) and offers **Download** followed by the file name, which ends in `.srt`. The subtitles are never burned into the video: load the SRT in your player or your editing software.

## 15. Language

Video Producer exists in English and in French. Choose **English** or **Français** in **Video Producer › Preferences…**, setting **Language**, or click the `EN` or `FR` reminder at the left of the status bar, which opens the same window. The change is immediate and is saved for you alone, on the server; if the saving fails, a message says that the language changed for this session only. Until you choose, the page follows the language of your browser (French if it is French, English otherwise).

The **Preferences** window has five other settings: **Prompt language** (see below), **Preview quality** (**Best performance**, **Balanced** or **Best quality**, without effect), **Snapping by default**, **Framing guides** and **Single-key shortcuts** (chapter 16). Except **Prompt language**, which is saved with the project, they apply to the current session and are not saved.

What is translated: the menus, the windows, the buttons, the tooltips, the messages, the names given to new items (for example a new shot or a new track), the prompt library with its templates, categories and composer choices, and the way numbers and durations are written. What is never translated is the content of your project: your own texts (the synopsis, the global direction, the shot prompts, the names and titles you typed, the project name) and the starter project, which is created once and is not translated afterwards. Product terms such as Director AI, Storyboard, Edit Engine, Control video or FL2VA are the same in both languages.

### Prompt language

Each project has its own **Prompt language**, English or French. It is the language of the texts that are sent to the models, the global direction and the shot prompts, and it does not depend on the language of the interface. It is English by default.

Change it in **Project properties…** (the setting says "Language of the direction and prompts sent to the models. Changing it does not rewrite existing text.") or in **Preferences…** (the setting says "Applies to the current project"). It is saved with the project. A new project always starts in English, whatever the language of the interface or of the project that is open.

What it changes:

- **The starter project.** Its global direction and its shot prompts are written in English, even when the interface is in French. Its name, synopsis, shot names, title and marker follow the language of the interface.
- **The prompt library.** The text that the built-in templates insert, their placeholders (the subject, the place and so on) and the default values of those placeholders are written in the prompt language. The names, descriptions and categories of the templates follow the language of the interface.
- **The composer.** The **Final prompt** is composed in the prompt language. The choices you click keep the language of the interface.
- **The direction checks.** The checks that read your texts use the rules of the prompt language: the contradictions between the global direction and a shot prompt (for example a direction that excludes neon and a prompt that asks for it). A text written in the other language is not checked.
- **The assistant.** It writes every shot prompt, rewrite and proposed shot in the prompt language of the project, and answers you in your own language. The contradiction checks it runs use the rules of that language.

What it never changes: nothing you typed is translated, and changing the setting rewrites no existing text. Set the language before you write, or rewrite the texts yourself.

## 16. Keyboard shortcuts

The table gives the shortcuts for Windows and Linux. On a Mac, read ⌘ for Ctrl, ⌥ for Alt and ⇧ for Shift; the menus and the tooltips show the notation of your system, and the side panel is ⌃⌘1 (Control and Command). **Search commands…** (Ctrl+K) finds any command, and **Keyboard shortcuts** (Ctrl+/) lists those that have a shortcut. The menus, the command search and that window show only the shortcuts that work. **Redo** has two: Ctrl+Shift+Z, which the menus, the tooltips and the command search show, and Ctrl+Y, which the **Keyboard shortcuts** window shows next to it.

| Shortcut | Action |
|---|---|
| Ctrl+K | Search commands… |
| Ctrl+/ | Keyboard shortcuts |
| Ctrl+, | Preferences… |
| Esc | Close, in this order: the command search, the open window, the open menu, a take preview or comparison; otherwise clear the selection, picked shots included |
| Ctrl+Z, Ctrl+Shift+Z | Undo, Redo |
| Ctrl+Y | Redo (second shortcut) |
| Ctrl+S | Save |
| Ctrl+O | Open… |
| Ctrl+I | Import from the library… |
| Ctrl+Alt+I | Import from this computer… |
| Ctrl+E, Ctrl+Shift+E | Export video…, Export to other software… |
| Ctrl+G | Generate selection: queues the target (the picked shots, otherwise Shot, Range or Sequence), even while takes are running |
| Ctrl+Alt+G | Generation queue |
| Ctrl+Shift+G | Make take final |
| Ctrl+J | PotionUI assistant (opens the chat in the Video Producer assistant mode) |
| Ctrl+Alt+1 | Side panel |
| Alt+1, Alt+2, Alt+3, Alt+4 | The views of Director AI: Review, Direction, Bible, References (from any workspace) |
| Space | Play / pause |
| Ctrl+B | Split at playhead |
| Ctrl+Shift+B, Ctrl+Alt+B | Slice the selected audio clip into slices of the length set in the Inspector, Join its slices |
| Ctrl+D | Duplicate |
| Backspace, Delete | Delete (several picked shots: all of them, in one step; a selected audio track: delete it after a confirmation) |
| A, R, B | Select tool, Range tool, Blade tool |
| I, O | Set in point, Set out point |
| Alt+X | Clear range |
| Alt+[, Alt+] | Trim start to playhead, Trim end to playhead |
| M | Add marker |
| N | Snapping |
| F, U, Alt+Backspace | Favorite, Remove flag, Reject |
| Left arrow, Right arrow | Move the playhead by one frame, 1/fps of the project (1 s with Shift) |
| Left arrow, Right arrow (Storyboard) | Select the previous or next shot |
| Home, End | Go to the start, Go to the end |
| Home, End (Storyboard) | Select the first or the last shot |
| D | Synopsis and breakdown (the left panel in the grid) |
| T, E | The takes of the selected shot (in the monitor in the band), Shot editor |
| Up arrow, Down arrow (Storyboard) | In the grid: the shot above or below; in the band: previous or next take of the shot in the monitor |
| Enter (Storyboard) | In the band, with a take in the monitor: use the take |
| <, > (Storyboard) | In the band: shorten, lengthen the selected shot by 0.5 s |
| Ctrl+Shift+Left arrow, Ctrl+Shift+Right arrow (Storyboard) | Move the selected shot one place earlier or later |
| Shift+R (Storyboard) | In the band: compare the seam with the previous shot |
| Ctrl+click (shots) | Add the shot to the selection, or take it out (grid, band, V1 track of the timeline) |
| Shift+click, Ctrl+Shift+click (shots) | Pick the shots from the chosen one to this one; with Ctrl, add them to the selection |

The single-letter shortcuts (A, R, B, I, O, M, N, F, U, D, T and E) can be turned off in **Video Producer › Preferences…**, setting **Single-key shortcuts**, which is on by default. Space, Backspace, Delete, the arrows, Home and End do not depend on it.

When the shortcuts work:

- Only while the focus is on the page and not in a text field. With a text field focused, a window open (a PotionUI picker or confirmation included) or the command search open, the other shortcuts are off; Esc, Ctrl+K and Ctrl+/ always act. While the PotionUI chat is open, the shortcuts of the page are off, except Undo and Redo (Ctrl+Z, Ctrl+Shift+Z, Ctrl+Y) outside a text field, so that you can take back a change of the assistant without closing the chat.
- Ctrl+G is the exception: from a text field of the page, it first commits the field (the prompt of the quick edit, for instance), then queues. In an open window, such as the shot editor, it does nothing. Ctrl+G and Ctrl+Shift+G never go to the find bar of the browser (its find next or previous), wherever the focus is.
- A combination acts only with exactly its keys. Ctrl+Shift+I and Ctrl+Shift+J (on a Mac Option+Command+I, J or K) stay with the developer tools of the browser, and the Alt+Left arrow of the browser keeps going back. The page never takes the combinations that manage the tabs and windows of the browser (Ctrl+N, Ctrl+T, Ctrl+W, Ctrl+Tab, Ctrl+1 to Ctrl+9), its address bar (Ctrl+L), its page search (Ctrl+F) or the clipboard (Ctrl+C, Ctrl+V): for the workspaces, a new project or a new title, use the menu, the buttons or the workspace selector. On Linux, Chrome and Firefox keep Alt+1 to Alt+8 for their tabs: open the Director AI views from the **Window** menu or the summary instead.
- A key held down does not repeat a command that switches something (Space, M, N, F, U, Ctrl+S, Ctrl+G, Ctrl+D and the like). Undo, Redo, Delete and the arrows do repeat.
- On a Mac, Ctrl+K in a text field stays with the text editor; the command search is ⌘K. The / of Ctrl+/ needs Shift on some keyboard layouts, such as the French one: the page accepts it either way.

### Keyboard and screen readers

Every button has an accessible name, and an icon button shows its tooltip when it receives the keyboard focus, not only when the mouse hovers it. The Tab key reaches every control with a visible focus ring, including the first choice of a window that you opened with the mouse. The trim and fade handles of the timeline are mouse handles that Tab skips: use the **Cut** menu and the Inspector instead (chapters 3 and 7). A screen reader hears the progress of a generation or of an export at each 10 %, or when the step changes, and never more than once every 3 seconds.

## 17. Troubleshooting

- **The Production bar shows no engine.** The pop-up reads "No engine". Your admin has not finished the setup: an engine, a video preset assigned to you, or a video model turned on for the cloud provider. Ask them to open Admin → Plugins → Video Producer.
- **The estimate shows "—" for the time.** Nothing has been measured yet for this preset, engine and resolution (the calibration is empty). It fills in after a few generations.
- **"Will stream through host RAM, slower."** The memory estimate is above what the GPU has. The generation is not blocked. If the server lacks free memory for it, the engine refuses to start and the take fails (`host_ram_oom`).
- **The quota is spent.** **Generate selection** says "GPU quota exceeded" until the next month or until your admin raises the limit of your plan. Running generations are not stopped, and a take that fails or is cancelled gives its minutes back. The first takes of a preset count 10 seconds of GPU for every second of video, which can look generous until the real durations are measured.
- **Generate selection is disabled.** Read the message in the bar: no range, no direction and no shot prompt, an empty prompt, no engine, a preset that is not yours, a profile the engine cannot generate, models to install, a cloud model to pick, or the quota.
- **"Models to install for this preset: …".** Your admin has not downloaded the model files that preset needs. Ask them.
- **A warning says the shots will be generated from text only.** The FL2VA profile has no frame linked to the shot. Add a start or an end frame (**Use the previous shot’s last frame** takes the first one from the previous shot, chapter 12), or pick another H3 profile; the generation is not blocked.
- **A take stays Queued.** Your admin limits how many generations you can have in progress at once: the take starts by itself when one of yours ends, in the order of the queue. The generation queue (the list button of the Production bar) shows its place; **Move to the head of the queue** makes it the next one. If it stays Queued while nothing of yours is running, tell your admin.
- **A take failed.** The card explains the usual causes in your language (for example "The server’s GPU ran out of memory: try a lower resolution or fewer frames."); for any other cause it shows the reason that PotionUI gives (in English) or, when it gives none, "The generation failed" followed by a code. **Retry** starts a new take for the same shot with the same seed. Typical causes: the GPU ran out of memory (`cuda_oom`: try a draft, a shorter shot or another engine); a model file is missing on the server (`missing_model_file`: ask your admin to download it again); the server ran out of memory while streaming the model (`host_ram_oom`). If PotionUI was restarted during the generation, the take is marked failed and cannot resume: use **Retry**. If every take then fails within seconds after an out-of-memory error, tell your admin: the server may need a restart.
- **"Upscaler not available" in Make final.** No upscaler is assigned to you: SeedVR2 enlarges the takes of Wan, LTX, MiniMax H3 Fast and VDN, the (12 GB) presets and cloud models. Use **Re-render at full resolution**, or ask your admin about SeedVR2.
- **References are ignored with MiniMax H3.** Ask your admin to check the model file picked for the References mode. The engine ignores the references of a profile other than Ref2VA, and of any other preset.
- **I closed the page during a generation.** The takes go on; open the project again to find them. The notifications tell you when they end.
- **The export window says "ffmpeg is missing on the server: video exports need it."** The server cannot find ffmpeg, so no video can be made. Ask your admin to install it; once it is, reload the page. The files for other software and the subtitles still download.
- **"No shot has a video file to export yet."** No shot of your saved project has a video or image file the server can find: every shot is still "To generate", or the media were removed from your library or gallery. Generate or import the shots, then export again. A single shot without a file does not stop the export: it is black and silent in the video.
- **"An export of this project is already running."** A project has one export at a time. Wait for it, or click **Cancel** on its card.
- **"The export folder is full: delete older exports and try again."** Your exports have used your size budget. Delete some in **Previous exports** (the copies in your library stay), or ask your admin for a bigger export budget.
- **An export stays Queued.** The server makes one export at a time, for everybody, so yours waits its turn. If it never starts, tell your admin.
- **"Converting the video" takes long.** A long sequence at 4K can take many minutes on a small server; the percentage shows how far it is. The export fails with "The video could not be converted." only if ffmpeg stops making progress for 5 minutes. Export at 1080p or 720p to go faster.
- **An export is Failed.** The card says what failed and, under it, the message of the server. "ffmpeg could not assemble the video." can come from a file ffmpeg cannot read, or from PotionUI restarting during the export ("The server stopped during the export."); start it again, and if it fails again give the message to your admin. "The export could not be saved." means that your PotionUI storage is full, for a web or social video, or that the server's disk is: free some space and export again.
- **A shot is black or silent in the video.** The server found no file for that shot (media removed from your library or gallery), or the file has no soundtrack, or its sound is muted: the shot or the track V1 is muted, or an audio track is soloed without V1 (chapter 13).
- **An FCPXML, OpenTimelineIO or EDL file does not find its media.** The paths in the file are paths on the PotionUI server. Copy the media to your editing computer and relink them in your software (chapter 14).
- **"This export no longer exists." or "The video is not ready yet."** when you download: the export was deleted, or it is still running. Export again, or wait for the end of the card.
- **A seam frame is refused.** "This shot has no previous shot." (the first shot cannot take one); "“Shot 1” has no take or video yet." or "The previous shot has no take or video to take a frame from." (generate and choose a take for the previous shot first); "ffmpeg is missing on the server: the last frame cannot be taken." (tell your admin); "The image could not be extracted from the take." or "The image could not be extracted: try again." (try again, and tell your admin if it persists); "The project could not be saved: no image extracted." (the project must be saved first: see the save state in the project bar).
- **The project bar says "Not saved — retry".** The last save failed: the connection dropped, or the server refused the project. A message tells which. Click the save state or the **Retry** button of the message to try again. Your changes stay in the page and the next change tries again too. Until a save works, opening another project or restoring a version asks you to confirm before it drops those changes. If the message says that the content was refused or that the project is too large, ask your admin: reloading the page would lose the changes that are not saved.
- **"Project reloaded: it changed elsewhere".** The project was saved from another tab, window or device after you opened it, so the page loaded the saved version. The changes you had not saved in this page are lost. Work on a project in one place at a time; **File › Version history…** brings back an earlier state.
- **"This project was deleted elsewhere".** The project was deleted from another tab or device while it was open here. The page opened your most recently modified project, or created the starter project. The changes you had not saved are lost.
- **A media does not show or play.** The viewer says **Media offline** ("The source file of “…” is no longer available: import it again or choose a take.") and so does the thumbnail of the shot on the timeline: the file is no longer available in your PotionUI library or gallery. Import it again, or choose a take for the shot. A take whose generation you deleted from the gallery no longer plays either.
- **"1 file could not be imported" (or "N files could not be imported").** The file is no longer available in the library or the gallery, or its kind is not accepted by the window: images and videos for **Import from the library…** and **From the PotionUI gallery**, audio for **Import audio from the library…**.
- **"“…” could not be imported: …".** A file from the computer did not reach your library. The reason follows: the file is too large for the server, the connection was lost, or PotionUI refused it (its message is shown, for example when your storage plan is full). Free some room in your library or ask your admin, then import the file again.
- **The assistant does not answer, shows no card or acts on the wrong project.** See chapter 10, "If it does not work".


## 18. Glossary

| English | Français | Meaning |
|---|---|---|
| shot | plan | A clip of the film, one generation. |
| take | prise | One generated version of a shot: a real video made by the engine you picked. |
| draft | brouillon | A fast, lower-resolution take to judge motion and framing. |
| final | final | The chosen take, enlarged (upscale) or generated again at the largest resolution (re-render). |
| label | étiquette | Draft, Candidate, Rejected or Final: how you sorted a take. The Final take is the one the shot plays (chapter 9). |
| drafts per shot | brouillons par plan | How many takes the Generate buttons of a shot make at once, 1 to 8; the project number when the shot has none (chapter 8). |
| shot editor | éditeur de plan | The window that gathers the prompt, duration, frames, references, drafts and engine of a shot (chapter 4). |
| own engine | moteur propre | The engine, profile, quality or seed that a shot sets for itself in its shot editor, instead of the project's (chapter 4). |
| sound reference | référence sonore | A voice, a music or an ambience of the **Sound** family of references, sent with the generation of a shot (chapter 13). |
| reference track | piste de référence | An audio track checked **Reference for the generation**: its part under each shot goes with the generation, except the clips switched off on their own (chapter 13). |
| mixed onto the take | mixé sur la prise | Laid onto the finished take as its soundtrack, without guiding the picture: what LTX does with the sound of a shot (chapter 13). |
| generation queue | file de génération | Your takes waiting for the engine or in progress, in the order they run, shared by all your projects; the list under the queue button of the Production bar (chapter 8). |
| Prompt modified | Prompt modifié | The mark of a take made before the last edit of its shot (chapter 4). |
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
| motion guide | guide de mouvement | A video of the **Motion guides** family of references: with the Ref2VA profile, MiniMax H3 carries its motion over to the shot (chapter 8). |
| Control video | Control video | The type of the motion guide that a project made with an earlier version gets from the reference video of each 3D shot (chapter 5). |
| H3 profile | profil H3 | FL2VA, Ref2VA or Hybrid AV: what guides the generation. |
| mode | mode | A way the PotionUI chat works, with its own instructions and tools. This page uses **Video Producer assistant**; a conversation keeps its mode. |
| tool | outil | An action the assistant can run in your project: write a shot prompt, fix conflicts, split the synopsis, check continuity. |
| approval | approbation | The card where you accept (**Approve**) or refuse (**Reject**) what the assistant proposes. Nothing changes before you approve. |
| context | contexte | The summary of your project that the page sends to the assistant with each message (chapter 10). |
| export job | job d'export | A video export waiting or running on the server, with its state and its progress. Once it ends it stays in **Previous exports** (chapter 14). |
| mezzanine | mezzanine | The high-quality intermediate video that the server assembles first and then converts into the file you download. You never handle it (chapter 14). |
