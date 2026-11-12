# Video Producer: user guide

This guide shows you how to make a short film with Video Producer, from the first idea to the exported video. Chapter 2 walks you through a first film in eight steps; the other chapters explain each part of the page. Interface labels are written in **bold**.

Every button, panel and message is described in full in **Video Producer: complete reference**, in the same chapters. Both pages are in the **Documentation** page of PotionUI.

## 1. What Video Producer is

Video Producer is a page of PotionUI for making short films with AI video. You write a synopsis and split it into shots. For each shot, you generate a few quick draft takes, keep the best one and render it in final quality. Then you cut, match the colors, mix the sound and export the film. Open it from the **Video Producer** entry in the sidebar.

### What you need

Your PotionUI administrator prepares what the page runs on. Ask them if something below is missing.

- **An engine and a video preset assigned to you.** The engine is the machine or the cloud service that makes the videos. If the engine chip of the production deck reads "No engine", nothing is set up for you yet.
- **Patience.** Generation is real and takes time. On a 12 GB graphics card, count several minutes for a 5-second draft, and hours for a final render by upscale to 1080p. The **Estimated** cell of the production deck tells you what to expect before you start (chapter 8).
- **The right preset for the card.** A preset whose name ends with a card size, such as **(12 GB)**, is made for a graphics card of that size. On an 8 GB card, use **Wan 2.1 T2V 1.3B (8 GB)** or **Wan 2.2 TI2V 5B (8 GB)**. On a 12 GB card, use **MiniMax H3 (12 GB)**, **MiniMax H3 Fast (12 GB)** or **Wan 2.2 14B Lightning (12 GB)**. Ask your administrator which card the server has.
- **ffmpeg on the server**, to export a video and to start a shot from the last image of the previous one.
- **An upscaler** (SeedVR2 or RTX Upscale) assigned to you, for final renders by upscale (chapter 9).
- **An interpolator** (Video Tools or RTX Upscale) assigned to you, so that slow takes play smoothly in the film (chapter 9).
- **A language model** assigned to you, for the assistant (chapter 10). Everything else works without it.

**MiniMax-H3 and its license.** The **MiniMax H3** engines use a model whose license excludes use, and anything generated with it, in the European Union, the United Kingdom, the United States and South Korea without an individual authorization from MiniMax. It also asks a commercial product to display "MiniMax H3" prominently. Ask your administrator before you use it: Video Producer does not check this for you.

### The starter project

The first time you open the page, it creates a starter project, "Lumi’s potion", and opens it. It is a short tale: the witch Lumi brews a violet potion in her workshop and turns it to gold. Its four shots of 5 seconds are still to generate, and each one shows a feature of the page:

1. **The workshop** is made from its text alone.
2. **The potion** starts from the last image of shot 1 (chapter 12).
3. **Lumi** casts the character card of Lumi, with her picture, and the card of the workshop (chapter 4, The bible).
4. **From violet to gold** goes from a first image, the violet bottle, to a last image, the same bottle turned to gold.

The project also holds a synopsis, a global direction, a title, a marker and four empty audio tracks. Its three images are added to your media and to your PotionUI library. Every engine can generate every shot, but not every engine uses everything: the estimate tells you what each one leaves out. On your next visits, the page opens the project you used last.

## 2. Your first film in eight steps

**Help › Getting started** shows these steps as a list you can click. Try them on "Lumi’s potion", or start an empty project with **File › New project**.

1. **Create a project.** **File › New project**. In **File › Project properties…**, set the name, the film format (for example 16:9 or 2.39:1), the delivery resolution (720p to 4K) and the frame rate. Your project is saved as you work.
2. **Set the global direction.** Open the **Director AI** workspace, view **Direction**. Describe the world, the photography, the palette and the pacing. This text guides every shot. Characters and places that come back go in the **Bible** view, one card each.
3. **Add the references.** In **Director AI**, view **References**, add the pictures that must stay the same from shot to shot: faces, sets, objects.
4. **Split the film into shots.** In the **Storyboard** workspace, write the synopsis and click **Propose a breakdown**: each sentence becomes a shot. Keep the shots you want, then adjust the prompt of each shot. The assistant can make a real breakdown for you (chapter 10).
5. **Generate drafts.** In the production deck at the bottom, check the engine on its chip and keep the quality on **Draft**. Select a shot, or choose **Sequence** for all of them, then press the round button, **Generate selection** (Ctrl+G). You get draft takes A, B, and so on.
6. **Choose a take and render it in final.** In the **Review** view of Director AI, compare the takes. Mark the ones worth keeping **Candidate**, the others **Reject**, and click **Selected** on the one the shot should play. Then click **Final render…** on it to get it at full resolution.
7. **Edit, match and mix.** Trim and order the shots on the timeline, fix the color seams (chapter 12) and mix the sound in **Mix** (chapter 13).
8. **Export.** **File › Export video…** makes a video for the web or social networks. You can also export files for editing software and subtitles (chapter 14).

## 3. The screen

From top to bottom, the page has:

- **The menu bar.** Ten menus: **Video Producer**, **File**, **Edit**, **Cut**, **Shot**, **Production**, **Audio**, **View**, **Window** and **Help**. **Search commands…** (Ctrl+K) finds any command by name and runs it.
- **The project bar.** The button that shows or hides the side panel, the project name (click it to rename the project) and its save state; the five workspaces, **Media**, **Storyboard**, **Director AI**, **Mix** and **Play**; then **Import**, **Export**, **Assistant**, the command search and the button that shows or hides the Inspector.
- **The work area.** A left panel that changes with the workspace, the center (the viewer, the storyboard or a view of Director AI), and the **Inspector** on the right, which shows the settings of what you selected (chapter 7).
- **The timeline.** One row per kind of item: **Titles**, **Prompts**, **Frames**, the video track **V1**, the reference video tracks, and one row per audio track (**A1**, **A2**…). Drag a shot to move it, drag its edges to trim it, and drag the white handles at the top of a clip to set its fades.
- **The production deck.** In **Storyboard** and **Director AI**, under the timeline. It says what the next generation will make and holds the one main button of the page, **Generate selection** (chapter 8).
- **The status bar.** The language, the number of shots and the length of the film, the selection, the takes in the queue and, if your administrator set a limit, your **GPU quota** for the month.

A rule to remember: the Storyboard, the Inspector and Director AI only choose what to generate. The production deck is where you generate.

**Narrow windows.** Under 1280 pixels of window width, the left panel and the Inspector become drawers that slide over the page: open them with the first and the last buttons of the project bar. Under 640 pixels, the page asks for a wider window; your project stays saved.

## 4. Workspaces

Each workspace changes the left panel and the center. The Inspector follows your selection everywhere except in **Play**.

### Media

All the images, videos and audio files of the project. Import with **Library** or **From computer**, or drop files on the panel (chapter 6). Filter with **All**, **Images**, **Videos**, **Audio** and **Generated**, double-click a media to preview it, and drag it to the timeline.

### Storyboard

The Storyboard shows the shots of the film. It has two views, **Band** and **Grid**, chosen in its header.

#### The band

The band shows the shots to the time scale, so you can read the rhythm of the cut. Each shot is a block as wide as its duration. Under it, the band stacks its takes, the music and what the shot sends to its engine (its references and its sound). A marker between two shots shows the seam: green when it matches, orange when it needs a look.

Drag a shot to move it and drag its right edge to change its duration. Under the band, the **monitor** plays the cut and shows the end of the previous shot and the start of the next one. Next to it, the **quick edit** changes the name, prompt, duration and engine of the selected shot. Double-click a shot to open the shot editor.

#### Synopsis and breakdown

**Synopsis and breakdown** (D) opens a window under the band with three tabs:

- **Breakdown**: your synopsis and three ways to cut it into shots. **By sentence** makes one shot per sentence. **On the song** follows the parts of a song on a Music track. **Assistant** asks the PotionUI assistant. You can keep, rename, split, merge, move or remove each proposed shot, then click **Add N shots**.
- **To produce**: the drafts left to make and the shots to render in final, with **Generate their drafts**.
- **To check**: the seams to fix, the failed takes, the shots whose prompt changed after their takes and the shots without a prompt.

#### The grid

One card per shot, in order, with its number, duration, name, stage (**Source**, **To generate**, **Draft** or **Final**), its number of takes and its prompt. **Edit** opens the shot editor. When you edit a shot after its takes were made, its takes show **Prompt modified**. An orange alert on a card means the shot does not match the previous one: click it to see why and fix it (chapter 12). **Match colors (n)** in the header fixes every color seam at once.

#### Picking several shots

Ctrl+click a shot (⌘+click on a Mac) to add it to the selection, and Shift+click to pick every shot between two. Ctrl+G then queues all the picked shots, and Delete deletes them in one step. Esc clears the selection.

#### The shot editor

**Edit** on a card, or **Edit shot…** in the Inspector, opens the shot editor. It gathers everything a take of the shot is made from:

- **Shot prompt text**: what happens in the shot. Write it in English (chapter 15).
- **Cast**: the characters and the place of the shot, from the bible. Under it, **Prompt sent to the engine** shows the whole prompt the shot will send.
- **Dialogue**: the lines of the shot, each with its **Speaker**. MiniMax-H3 and LTX speak them with the mouth in sync; Wan and the cloud models leave them out.
- **Duration** and **Frames**: the **First frame** and the **Last frame** the take should start and end on. **Keep the framing** sends the first frame as the last one too, so the camera keeps its framing.
- **References**: the project references the shot sends (tick **Exclude** to leave one out) and its own references, including sounds.
- **Start and end images**: let an image model make a first or last frame from the pictures of the shot, or take them from the shots around it.
- **Drafts**: how many takes one generation makes, 1 to 8.
- **Engine**: give this shot its own engine, profile, quality or seed. **Back to the project** removes them.

**Save** applies everything, and **Edit › Undo** brings it all back. Saving never deletes a take.

#### Write the prompt

**Write the prompt**, above the shot prompt text, lets the language model of PotionUI write the prompt of the shot. Type in a few words what the shot should show, then click **Write** (or press Ctrl+Enter). The model reads your words, the shot's prompt as it stands, its start and end images and the prompting guide of the shot's engine, and proposes a prompt. Nothing changes until you choose: **Use this prompt** puts it in place of the shot prompt text, **Discard** leaves your prompt as it was. **Undo**, under the text, gives back your prompt of before, as long as you have not typed in it since. **Cancel** stops a writing that takes too long.

The model writes only what the camera sees, in English. The page still adds the cast cards, the global direction and the format of the engine, as for a prompt you type yourself. The button is greyed when no language model is set up for you: hover it to read why, and ask an admin to set one up. A model that cannot look at images writes from your words alone.

#### Card words of one shot

When a picture of a cast card goes with the shot (MiniMax-H3 with the Ref2VA profile), the shot editor shows **Card words beside a picture** under **Prompt part from the references**. **As the project** follows **File › Project properties…**; **Description**, **Label** or **Picture only** apply to this shot alone. **Prompt sent to the engine** shows the result.

### Director AI

Director AI shows one of four views in the center. Open them from the left panel, the **Window** menu or Alt+1 to Alt+4. The left panel sums up the state of each view, the engine of the project, and **To check**: the conflicts with the direction, the cards a shot names without casting them, the failed takes and the seams to fix.

- **Review** lists the shots with their takes, filtered by **To review**, **Running**, **Selected** and **All shots**. Click a take to play it. The panel on the right explains what you chose: the prompt a take received, why a take failed and what to do, or how a seam looks. At the bottom, **Assemble chosen takes** puts every selected take in the cut.
- **Direction** holds the five fields of the global direction: world and intent, characters and identity, photography, palette and lighting, pacing and continuity. On the right, **Composed prompt** shows the prompt a sample shot would send. When a shot prompt contradicts the direction, an alert lists the conflict.
- **Bible** holds the cards of the recurring characters and places (see below).
- **References** holds the pictures, videos and sounds that guide the generation, as **Project** references (every shot) or for one shot. The panel on the right says what each engine really gets of a reference.

Only MiniMax-H3 with the Ref2VA profile sends the reference pictures to the engine. The other engines receive the words of the cards instead (chapter 8).

#### The bible

The **Bible** view holds one card per recurring character and one per place. A card has a **Visual tag**, short and concrete ("the red-haired woman in the navy raincoat"), a fixed description, and its **Identity images**. Cast a card in a shot in the shot editor, the Inspector or the **Cast shot by shot** grid: its words then go into the prompt of that shot.

Write the visual tag of each cast character in the shot prompt, the same way: the page warns you when it is missing. Text alone does not hold a face from shot to shot; a consistent first frame, or Ref2VA references, work better.

**File › Project properties… › Card words beside a picture** sets how much of a card goes with its picture in Ref2VA: **Description** (the default), **Label** or **Picture only**.

A character card can also hold a **Voice description**, a **Spoken language** and a **Voice reference** for its lines.

### Mix

The left panel lists the sounds of the project and the roles (**Dialogue**, **Music**, **Ambience**, **SFX**). The mixing console takes the place of the timeline: faders, mute and solo, pan, equalizer, compressor, filter, reverb and delay sends, and meters (chapter 13).

### Play

The cut played in a large viewer, with the timeline under it and no side panels. Space plays and pauses; the arrows move by one frame.

## 5. Projects

Your projects are saved on the PotionUI server, in your account, as you work. There is no file to keep. The page opens the project you used last.

### Saving

The page saves by itself, less than a second after your last change. The project bar shows the state: "Saved at" and the time, "Modified · click to save", "Saving…" or, when a save failed, "Not saved — retry". Click the state to save at once, or press Ctrl+S. If a message says the project is too large or its content was refused, a retry will not help: ask your administrator.

### Open

**File › Open…** (Ctrl+O) lists your projects, the most recently modified first. Select one and click **Open**. **New project** creates an empty project. The trash icon deletes a project after a confirmation; its media stay in your library and the videos of its takes stay in your generation history.

### Version history

Each save creates a version. **File › Version history…** lists them; select one and click **Restore** to go back to it. A restore is itself a new version, so you can always come back. Your administrator sets how many versions are kept per project (50 by default).

### When the project changed elsewhere

If the same project is open in two tabs, or the assistant changes it while you work, the page merges both sides. When both changed the same thing, your version wins, and the page says so. Ctrl+Z undoes the merge.

### Undo and redo

**Edit › Undo** (Ctrl+Z) and **Redo** (Ctrl+Shift+Z or Ctrl+Y) work on your changes in the page, up to 100 steps. Opening another project or reloading the page empties the history.

## 6. Media

The media of a project are the images, videos and audio files you imported, and the takes of the project.

### Importing

- **From the library**: **File › Import from the library…** (Ctrl+I), or the **Library** buttons. You pick files of your PotionUI library.
- **From the gallery**: **File › From the PotionUI gallery** lists your past generations.
- **From this computer**: **File › Import from this computer…** (Ctrl+Alt+I), the **From computer** buttons, or drop files on the Media panel or on the timeline. Each file is sent to your PotionUI library, then added to the project.

Accepted files: images (`.jpg`, `.jpeg`, `.png`, `.gif`, `.webp`, `.bmp`), videos (`.mp4`, `.webm`, `.mov`, `.mkv`, `.avi`) and audio (`.wav`, `.mp3`, `.ogg`, `.flac`, `.m4a`, `.aac`). The size limit is the one of your PotionUI storage plan.

An imported media is a link to the file in your library or gallery. If you delete that file from PotionUI, the project can no longer show it: the viewer says **Media offline**.

### Import a cut as shots

To start from an existing edit, an animatic or a reference film, choose **File › Import a cut as shots…**. It is also in the **Import** menu of the project bar (**A cut, split into shots…**), and under a selected video of the Media panel (**Split into shots…**).

1. Pick the video: one of the project, **From the library…** or **From this computer…**.
2. Set **Sensitivity** (higher finds softer cuts too) and **Shortest shot** (two cuts closer than this count as one).
3. Choose what **Each piece becomes**. **The shot's source** places the piece on its shot, with its sound: you get the original cut, ready to be replaced shot by shot. **Its motion reference** leaves the shot to generate and keeps the piece as its Motion reference, which MiniMax-H3 follows in Ref2VA.
4. Choose where to **Place the shots** (**At the end**, or after the selected shot), then click **Find cuts**.

PotionUI finds the cuts and Video Producer makes one shot per cut. One **Undo** removes all the new shots. The pieces are saved in your PotionUI library and stay there after an Undo. A video with no cut, or with more than 200 shots, is refused with a hint to change the settings.

### Removing a media

The trash icon of a media removes it from the project, after a confirmation that says where it is used. The file stays in your library, and **Undo** brings everything back.

## 7. Inspector

The Inspector, on the right, shows the settings of what you selected. For a shot, it has three tabs:

- **Shot**: **Edit shot…**, **Final render of take A…**, the duration and the source, the **First frame** and **Last frame**, the fades, the sound of the shot, the cast, the dialogue and the flag.
- **Takes**: the takes of the shot, grouped by label (chapter 9).
- **Color**: the luminance scope, the match with the previous shot, color presets and fine settings (chapter 12).

An audio clip, a title, a shot prompt, a reference frame, a marker, a reference or a console strip each has its own panel. With nothing selected, the Inspector shows the project and **Project properties…**. In Director AI, each view shows its own panel in place of the Inspector.

## 8. The production deck and generation

The production deck sits at the bottom of **Storyboard** and **Director AI**. Generation is real: a take is a video made in the background by the engine you picked. You can leave the page while it runs.

### What the deck shows

From left to right:

- **The state**: what the deck will generate and where it stands, with the actions that fit. A coloured dot gives the state: **Ready** (grey), **Can't generate yet** (amber, with the reason), **Generating** (with the progress), **Done** (green) or **Failed** (red, with **Retry**).
- **The target and the button**: **Shot**, **Range** or **Sequence** (or **3 shots** when you picked shots), the round **Generate selection** button (Ctrl+G), and the quality, **Draft** or **Final**. While takes run, the round button cancels them.
- **The tools**: the **Estimated** cell, the engine chip, the generation queue and **More**.

When the deck says **Can't generate yet**, its reason usually comes with a button that fixes it: **Edit the shot**, **Open the Direction** or **Choose an engine**. Some reasons need your administrator: a preset that is not assigned to you, model files to install, or ffmpeg missing on the server.

### The estimate

The **Estimated** cell shows the expected time and, for a local engine, the GPU memory. Click it for the details: the shots and takes, the time, the memory, your GPU quota and, for an administrator, the cost of a cloud model. The time comes from the takes you already made with the same preset and size, so it reads "—" until the first ones are done. Warnings in amber do not block the generation; they tell you, for example, that a shot will be made from its text only because the engine ignores its frames.

If your administrator limits your GPU minutes, a generation that would exceed what is left this month is refused. A take that fails or is cancelled gives its minutes back.

### The engine and its settings

The engine chip shows the engine, the profile, the size and the number of drafts, for example "MiniMax H3 (12 GB) · FL2VA · 832×480 · ×2". Click it to open the **Generation settings** drawer:

- **Engine**: the presets and cloud models your administrator enabled for you.
- **Profile**: what guides the generation (see Profiles below).
- **Draft size** and **Final size**: the size of the takes for each quality. **Auto** is a good default.
- **Drafts per shot**: how many takes a generation makes per shot, 1 to 8.
- **Edit Engine**: every option of the engine (speed, steps, models, LoRAs…), as its preset defines them.

A shot can set its own engine, profile, quality and seed in its shot editor (chapter 4).

### Quality

**Draft** makes quick takes at a small size, to judge the motion and the framing. **Final** makes takes at the largest size of the engine. To improve a draft you like, **Final render…** is usually better (chapter 9): it keeps the picture you chose.

### Generate

1. Choose the target: select a shot (**Shot**), draw a range on the timeline (**Range**), choose **Sequence** for the whole film, or pick several shots with Ctrl+click.
2. Press **Generate selection** or Ctrl+G.

Each shot gets as many takes as its number of drafts, each with its own seed. You can press Ctrl+G again while takes are running: the new takes join the queue. A shot that starts from the previous one waits for the take of that shot (chapter 12).

### Follow the takes

The deck, the Storyboard card and the block of the shot on the timeline show the step and the progress of each take. When a batch ends, a message says how many takes are ready, with **View**, and PotionUI sends a notification. **Cancel** on a take card stops that take; the round button of the deck stops them all.

**The queue.** The list button of the deck (or Ctrl+Alt+G) opens the generation queue: your takes waiting or in progress, for all your projects. **Move to the head of the queue** makes a waiting take the next one. Your administrator limits how many of your takes run at once; the others wait as **Queued** and start by themselves.

### Profiles

The profile says what guides the generation. The page greys the profiles the chosen engine cannot run.

| Profile | What guides the take | Engines |
|---|---|---|
| FL2VA | The first and last frames of the shot, and its text. A shot without a frame is made from its text alone. | All engines. |
| Ref2VA | The references: the pictures of the characters, places and objects, motion videos and sounds. | MiniMax-H3 and MiniMax-H3 (12 GB); LTX-2.5 through a reference sheet, once your administrator installed it. |
| Hybrid AV | Like FL2VA; the model makes the picture and the sound together. | MiniMax-H3 and its variants. |

With Ref2VA, MiniMax-H3 takes up to 9 images, 3 videos and 3 sounds per shot. A video made with LTX-2.5 falls under the license of Lightricks, which asks you to say that it is generated by AI where the law requires it.

### Reference video tracks

A reference video track gives MiniMax-H3, in Ref2VA, a video to follow. Add one with **Add › Reference video track** in the timeline toolbar, then drop a video on it. Its role is **Motion** (the shot moves as the video does) or **Continuation** (the shot continues the video). Other engines and profiles ignore the track, and the estimate says so. A finished take can become a reference too, with **To the references** on its card.

## 9. Takes and final render

A take is one generated video for one shot. Its video is an ordinary PotionUI generation: it stays in your generation history even if you delete the take here.

Two words are easy to mix up. A take is **Selected** when it is the one its shot plays. A take is of **Final** quality when it was made at full resolution. A selected take can be a draft.

### The take card

The card shows the letter of the take, its quality, the engine that made it, its label and its state. Click its picture to preview it. **Take details** shows the profile, the size, the seed and the server that made it. A failed take explains the usual causes in plain words, with **Retry**. The card also offers **Compare**, **Extract a frame at the playhead** (chapter 12), **Generation details** and **Delete**.

For a one-off retouch of a take (a free crop, a speed-up, an effect), open it from **History**: in the take's **Tools** menu, choose **Edit**, then the tool you need. The take opens in PotionUI's Video editor with that tool ready. Saving puts the result in your library, and **Import › From the library…** brings it into the project.

### Labels

Every take has one label:

- **Draft**: a new take.
- **Candidate**: a take worth keeping.
- **Rejected**: a take you do not want. **Hide the rejected takes** hides them without deleting them.
- **Selected**: the take the shot plays. Only one per shot.

The first draft that finishes for a shot without a take is selected for you, and so is a finished final render. **Assemble chosen takes**, at the bottom of the **Review**, puts all the selected takes in the cut.

### Final render

**Final render…** on a draft opens a window with two or three ways:

- **Upscale** (the default) enlarges the take as it is: the motion does not change. Pick the **Upscaler**: **Automatic**, **Fast (RTX)** (seconds, sharp, adds no detail), **SeedVR2** (slow, restores detail) or, for a take of the base MiniMax-H3 preset, **Engine**. Then pick the **Target resolution**; **Auto** gives the size the film needs.
- **Re-render at full resolution** generates the shot again at the largest size, with the same seed. The subject and the look stay, but the layout of the picture changes.
- **Guided render**, when your administrator installed it, renders the shot again with LTX-2.5, following the motion and framing of the take.

If no upscaler is assigned to you, the window shows **Upscaler not available** and offers only the re-render. The final render becomes a new take of **Final** quality, and it is selected on its shot when it ends.

### The frame rate of the takes

A take keeps the frame rate of its engine (Wan 16 fps, MiniMax-H3 24 fps, LTX 25 fps), and the film has its own. A take much slower than the film stutters in the export, because frames repeat. **Conforming** makes a version of the take at the frame rate of the film, by frame interpolation: the **Export** window and **Final render of the film** offer it, and **Project properties… › Interpolator** chooses how. It needs an interpolator assigned to you: **Video Tools** (RIFE 4.25) or **RTX Upscale** (NVIDIA Frame Generation).

### Slow motion

**Speed** (100 %, 50 % or 25 %), in the Inspector and the shot editor, plays a take slowed down. The shot lasts longer to match, and the sound of the take is muted. For a smooth export, the take needs a version at a higher frame rate, made like a conform: **Prepare** in the Inspector, or the export window, makes it.

### Final render of the film

Once every shot has a selected take, **Production › Final render of the film…** (also in the Storyboard header and at the bottom of the **Review**) renders all of them in final quality at once. Choose the method once (**Upscale**, **Guided render** or **Render again**) and the upscaler. The window lists each shot with its state, skips the shots already in final quality, and names the shots that have no selected take yet. **Start the final render of N shots** queues them all; open the window again to follow them or cancel the pass.

## 10. Assistant

The assistant is the PotionUI chat, in its own mode for this page, **Video Producer assistant**. It reads your project and can work on it for you: write and fix shot prompts, cut your synopsis into shots, add, change, order and delete shots, check the continuity, generate takes, label them, assemble the edit and export the video.

Two kinds of change:

- **What costs or cannot be taken back waits for you.** Rewriting a prompt, deleting shots, generating takes and proposing a breakdown show a card with a preview. Nothing happens until you click **Approve**.
- **The rest is done at once.** Adding and changing shots, labelling a take, assembling and exporting are saved right away, and Ctrl+Z takes each one back.

### Before you start

- Your administrator must give you a language model that can call tools (Admin › LLM / Assistant). Without one, the chat says "Chat is currently unavailable".
- Keep the Video Producer page open on your project while you chat: the assistant only knows your project while the page is open.

### Open the assistant

Click **Assistant** in the project bar, choose **Window › PotionUI assistant**, or press Ctrl+J. The chat opens over the page, and its header reads **Video Producer assistant**. A conversation started elsewhere in PotionUI keeps its own mode: click **start a new chat** from this page.

### Requests to try

Write in your own language. Select a shot first and the assistant knows which one you mean, or name it ("shot 3", or its name).

- "Write the prompt of the shot “The gulls”: a low angle on the water, backlit." A card shows the new prompt; **Approve** applies it.
- "Fix the conflicts between my direction and my shot prompts." One card rewrites every conflicting prompt.
- "Cut my synopsis into shots of about 5 seconds." The proposal opens in the Storyboard, where you keep the shots you want.
- "Check the continuity between my shots and tell me what to fix." The answer appears under **To check** in the left panel of Director AI.
- "Add a close-up of Mara’s hands after “The gulls”, 3 seconds, with Mara in the shot." Done at once; Ctrl+Z undoes it.
- "Generate a draft of shots 1 to 3." A card shows the takes, the engine, the GPU minutes and the time; nothing starts before **Approve**.
- "Select take B of “The gulls”." Or "Put the selected takes in the edit and export the video for the web."

### What it does not do

The assistant does not edit the synopsis, the direction, the bible cards, the titles, the color, the sound or the mix. It does not choose the engine, render the film in final or import media: it answers in text, and you do it on the page. It writes every prompt in English and answers you in your language. Each of its changes is a new version of the project, marked "Assistant" in **File › Version history…**.

### If it does not work

- **"Chat is currently unavailable".** No language model is assigned to you: ask your administrator.
- **The assistant answers but never shows a card.** Check that the **Tools** button of the chat box is on and that the Video Producer tools are ticked. The model may also be unable to call tools: ask your administrator for another one.
- **The assistant does not know your project.** The conversation was started in another mode. Click **start a new chat** from the Video Producer page.
- **A card failed with `version_conflict`, `project_not_found` or `shot_not_found`.** The project changed meanwhile. Reopen it with **File › Open…** and ask again.
- **The assistant says the takes cannot start.** It gives the same reason as the production deck (chapter 8).

The complete reference lists the other cases, including the settings your administrator can change for slow or forgetful models.

## 11. Prompts: library and composer

**Window › Prompt library**, or a **Library & assistant** link next to a text, opens the window **Prompt library & assistant**. It writes into the field it was opened from: a field of the global direction or a shot prompt.

- **Library**: templates in nine categories (Cinema, Camera, Lighting, Film styles, Dialogue, Photography, Sound, Continuity, To avoid). Fill in their variables, edit the preview, and click **Insert**. **Save to Personal** keeps your own version; the star marks a favorite.
- **Composer**: builds a prompt from a camera movement, a lighting, a film style and an acting intent, for the profile you pick.
- **Ask the PotionUI assistant** closes the window and opens the chat with a request already typed.

**Add to the text** adds the template to the field; **Replace** replaces the field.

## 12. Color and continuity

Continuity is about the seams, the cut from one shot to the next. Video Producer measures every seam, warns when two neighbor shots do not match, fixes the color in one click, and can start a shot from the exact image where the previous one ended.

### Color match

When two neighbor shots do not match, an alert says that a shot is brighter, darker, warmer or cooler than the previous one. **Match** (**Match color** in the Storyboard) fixes it by adjusting exposure and temperature. **Match colors (n)** fixes every seam at once. The **Color** tab of the Inspector also has six presets and fine settings (**Exposure**, **Contrast**, **Saturation**, **Temperature**), with **Reset** and **To all shots**.

**Auto match**, in the same tab, corrects a take from an **Anchor** image, such as the first frame of the shot. Choose its **Strength** and compare the **Anchor**, **Take** and **Matched** pictures. The export applies the same correction.

### The look of the takes

The server compares the overall look of the takes at each seam and with the pictures of the bible. It is not a face recognition: two people dressed and lit alike can pass, and the same character under another light can be flagged. Under a threshold, the seam or the take says "Look to check" or "drifts from the card", with a percentage, and **Compare the takes** shows them side by side. Your administrator may not have installed the models these measures need: the page then says that nothing is measured.

### Start a shot from the previous shot

With the FL2VA profile, a take starts on the first frame of its shot. Give a shot the last image of the previous shot, and the two shots join without a jump.

- **Use the previous shot’s last frame**, offered on the alerts, in the seam panel and in Inspector › Shot › Frames, takes that image now and sets it as the **First frame** of the shot. Nothing is generated; the next take starts from it.
- **New shots start from the previous one.** A shot you add after another takes its last image as first frame by itself. Turn this off in **File › Project properties…**, **Start each new shot from the previous one**.
- **The link chip** next to the number of each shot shows and switches whether the shot starts from the end of the previous one. The switch **Start from the end of the previous shot** does the same in the Inspector and the seam panel.

When you generate several chained shots at once, each take waits for the take of the previous shot, takes its last frame, then joins the queue: the card says "Waiting for take A of “Shot 2”". If the previous take fails, the chained one fails too, and **Retry** starts it again.

**Chain by.** In **File › Project properties…**, or for one shot under its chain switch, **Chain by** chooses how a chained shot follows the previous one. **Last frame**, the default, starts it from the last image. **Continuation** sends the last 2.33 seconds of the previous take, with its motion and sound, to MiniMax-H3: in Ref2VA as a continuation video, and with MiniMax-H3 (12 GB) or MiniMax-H3-Fast (12 GB) in FL2VA as a video to continue. Under the chain switch of a shot, its card says what the take will do (continue the previous take, or start from the last frame, from its text or from its references) and why, for example when the previous shot shows a still or is too short.

An engine that generates from text only, such as **Wan 2.1 T2V 1.3B (8 GB)**, does not use first frames. **Wan 2.2 14B Lightning (12 GB)** hands a shot that starts from an image to its image-to-video companion, when your administrator installed it.

### Extract a frame at the playhead

For another moment than the last image, put the playhead on the shot and click **Extract a frame at the playhead** on a finished take. In the first half of the shot, the image becomes its **First frame**; in the second half, its **Last frame**.

### Cross-dissolve between two shots

A cut can be a cross-dissolve: the picture of the shot that ends blends into the picture of the shot that starts. Select the shot that starts and choose its **Transition** in the Inspector (the window of a cut that carries a continuity alert in the Storyboard grid offers it too): **Cut**, or **Cross-dissolve** of 0.4, 0.6, 1, 1.2 or 2 seconds.

- **The film gets shorter by the length of the dissolve.** No frame is generated for it and each take keeps the length of its shot: the shot that starts moves earlier, and the later shots follow with their prompts and frames (the first dissolve of a project can also move earlier shots by a hair, when their lengths are off the 0.04 s grid). Sounds, titles and markers stay where they are, as when you trim a shot; move them if they must follow the picture. Under the choice, the page says how much shorter the film gets.
- A dissolve lasts at most half of the shorter of its two shots; the page says when it shortens the one you chose. The frame rate of the project does not change it.
- A shot that starts from the last frame of the shot before already continues its motion: with a dissolve on the same cut, that motion shows twice. The page says so under the choice.
- The blade does not cut inside a dissolve, nor where a piece would be too short for its dissolve.
- On a cut with a cross-dissolve, the fades to black of the two shots on that cut are not played: choosing a dissolve sets them to zero, and the Inspector greys them out.
- The sound of the two shots crosses over the same time. The **Crossfade between neighbouring clips** of the export window is another setting: it only joins the clips of the audio tracks and changes no duration.
- The timeline draws a crossed box on the cut (click the strip on its top to select the shot that starts) and each shot up to the middle of its dissolve. The viewer and playback blend the two pictures.
- The exported video holds the dissolve, and so do the FCPXML, OpenTimelineIO and EDL files.

## 13. Audio and subtitles

Audio lives in tracks, each with a role: **Dialogue**, **Music**, **Ambience** or **SFX**. **Audio › Add audio track** adds one, and **Audio › Import audio from the library…** or **from this computer…** brings sounds in. You can also drop audio files on a track.

### Tracks and the mixing console

Tracks are named **A1**, **A2**… by their place. To delete one, select it and press Delete, or right-click its name on the timeline. In the console, each track has a fader (double-click it for 0 dB), pan, effects (**Equalizer**, **Compressor**, **Filter**), sends to the reverb and the delay, and a meter. Everything you hear is what the exported video holds.

### Mute and solo

**M** mutes a track and **S** solos it, on the timeline and in the console; the video track **V1** has them too, for the sound of the shots. When a track is soloed, only the soloed tracks are heard, and mute wins over solo. **Mute this shot**, in Inspector › Shot, mutes one shot.

### Sound that goes with the generation

A shot can send sound with its generation:

- **Sound references**: a voice, a music or an ambience, in Director AI › References (family **Sound**) or with **Add a sound** in the shot editor.
- **Reference tracks**: an audio track switched to **Reference for the generation** in its Inspector. The part of the track under the shot goes with the generation. Each clip can follow its track or set its own switch.

What happens depends on the engine, and the shot editor, the Storyboard card and the estimate say which:

| Engine | What happens |
|---|---|
| MiniMax-H3 with Ref2VA | The sound guides the generation. A shot needs a picture or a video besides its sound. |
| LTX, and MiniMax-H3 outside Ref2VA | The sound is mixed onto the finished take, without guiding the picture. |
| Wan, cloud models and the other engines | Nothing is sent; the sound stays in your edit. |

To send only part of a long sound, cut it into slices: select the clip and use **Slice** in its Inspector (**Cut › Slice the clip into 5.0 s slices**, Ctrl+Shift+B), or **Slice on the shots** to cut it at the edges of the shots. Each slice has its own switch. **Join** (Ctrl+Alt+B) puts the slices back together.

### Subtitles

The titles of the timeline become the subtitles of the film. **File › Export subtitles…** exports them as an SRT file (chapter 14).

## 14. Exports

**File › Export video…** (Ctrl+E) opens **Export and share**, with three tabs: **Video**, **To other software** and **Subtitles**. Before the export, the window warns about shots that are not in final quality, rejected takes and unsolved direction conflicts. The export always renders the whole film.

### Video

Pick a format and a resolution (720p, 1080p, 1440p or 4K), then click **Export**.

- **Web · H.264 MP4**, in the aspect ratio of the project.
- **Social media · H.264**, in 9:16, 4:5 or 1:1; the shots are cropped around their center.
- **Master file · ProRes 422 HQ**, a MOV for editing and grading software.
- **Archive · H.265 10-bit**, a compact, high-quality MP4 to keep.

Options:

- **Audio stems by role**: five WAV files besides the video, one per role and one for the sound of the shots, in a ZIP.
- **Level**: **As mixed**, **Web and social · −14 LUFS** or **Broadcast EBU R128 · −23 LUFS**.
- **Crossfade between neighbouring clips**: none, or 0.25 to 1 second.

The video holds the shots with their color and fades, and the sound as the console plays it. Titles and markers are not in the video; subtitles are a separate file. If ffmpeg is missing on the server, the Video tab says so and **Export** is disabled.

### Follow the export

The export runs on the server, in the background: you can close the window or leave the page. Its card shows the step and the progress, and **Cancel** stops it. When it is ready, the card offers **Download** and PotionUI sends a notification. A web or social video is also copied to your library. The master and the archive stay in the export folder: download them from the window.

**Previous exports** lists the earlier exports of the project, with a download and a delete button. Your administrator sets a size budget for your exports; when it is full, your oldest exports are deleted to make room.

### Finishing

Under **Sound**, **Finishing** gives a web or social video a last touch with PotionUI's own effects: **Fix colours** (neutral whites and full contrast), a **LUT** your administrator installed, one of your **Looks**, a **Vignette** and **Film grain**. All are off by default: switch on the ones you want and set their strength. **Export** then reads **Export and finish**. When the export is ready, PotionUI encodes the film a second time with the finishing and saves it to your library as a new video. A second card follows the finishing, with **Cancel finishing**; when it is ready it offers **Download finished** and **Show in the library**. The plain export is always kept: if the finishing fails or you cancel it, the window says so and the plain file stays ready to download. The master and the archive are never finished. Your choices are saved with the project.

### To other software

Three files of the cut, for editing and grading software: **FCPXML** (`.fcpxml`), **OpenTimelineIO** (`.otio`) and **EDL CMX 3600** (`.edl`). They hold the order of the shots, their names and in points, and, for OpenTimelineIO, the audio tracks. They carry no fades, no color settings and no titles. A cross-dissolve between two shots is the exception: the three files write it as a transition (chapter 12).

The files point to the media as the server stores them. If your editing software runs on another computer, copy the videos of your takes there (download them from your gallery) and relink them in your software.

### Subtitles

An SRT file made from the titles of the timeline, in time order. Load it in your player or your editing software: subtitles are never burned into the video.

## 15. Language

Choose the language of the interface in **Video Producer › Preferences…**, setting **Language**, or click the language reminder at the left of the status bar. The choice is saved for you. Until you choose, the page follows the language of your browser.

The menus, windows, messages and the prompt library follow that language. Your own texts never change language, and neither does the starter project once it is created.

### Prompt language

Every prompt is in English: the global direction, the cards, the shot prompts, and everything the page or the assistant writes for you. The checks that compare a shot prompt with the direction only read English. A prompt you write in another language is sent as you wrote it, so write your prompts in English for the best results.

The **Preferences** window also has **Single-key shortcuts** (chapter 16), **Snapping by default** and **Framing guides**. These apply to the current session and are not saved.

## 16. Keyboard shortcuts

The table gives the shortcuts for Windows and Linux. On a Mac, read ⌘ for Ctrl, ⌥ for Alt and ⇧ for Shift; the menus and the tooltips show the notation of your system, and the side panel is ⌃⌘1 (Control and Command). **Search commands…** (Ctrl+K) finds any command, and **Keyboard shortcuts** (Ctrl+/) lists those that have a shortcut. The menus, the command search and that window show only the shortcuts that work. **Redo** has two: Ctrl+Shift+Z, which the menus, the tooltips and the command search show, and Ctrl+Y, which the **Keyboard shortcuts** window shows next to it.

| Shortcut | Action |
|---|---|
| Ctrl+K | Search commands… |
| Ctrl+/ | Keyboard shortcuts |
| Ctrl+, | Preferences… |
| Esc | Close, in this order: the command search, the open window, the open menu (the queue, **More** and the estimate details included), the Settings drawer, a side drawer, a take preview or comparison, the monitor of the Review, the seam comparison; otherwise clear the selection, picked shots included |
| Ctrl+Z, Ctrl+Shift+Z | Undo, Redo |
| Ctrl+Y | Redo (second shortcut) |
| Ctrl+S | Save |
| Ctrl+O | Open… |
| Ctrl+I | Import from the library… |
| Ctrl+Alt+I | Import from this computer… |
| Ctrl+E, Ctrl+Shift+E | Export video…, Export to other software… |
| Ctrl+G | Generate selection: queues the target (the picked shots, otherwise Shot, Range or Sequence), even while takes are running |
| Ctrl+Alt+G | Generation queue |
| Ctrl+Shift+G | Final render of the take… |
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

- Only while the focus is on the page and not in a text field. With a text field focused, a window open (a PotionUI picker or confirmation included), the Settings drawer of the deck or the command search open, the other shortcuts are off; Esc, Ctrl+K and Ctrl+/ always act. While the PotionUI chat is open, the shortcuts of the page are off, except Undo and Redo (Ctrl+Z, Ctrl+Shift+Z, Ctrl+Y) outside a text field, so that you can take back a change of the assistant without closing the chat.
- Ctrl+G is the exception: from a text field of the page, it first commits the field (the prompt of the quick edit, for instance), then queues. In an open window, such as the shot editor, it does nothing. Ctrl+G and Ctrl+Shift+G never go to the find bar of the browser (its find next or previous), wherever the focus is.
- A combination acts only with exactly its keys. Ctrl+Shift+I and Ctrl+Shift+J (on a Mac Option+Command+I, J or K) stay with the developer tools of the browser, and the Alt+Left arrow of the browser keeps going back. The page never takes the combinations that manage the tabs and windows of the browser (Ctrl+N, Ctrl+T, Ctrl+W, Ctrl+Tab, Ctrl+1 to Ctrl+9), its address bar (Ctrl+L), its page search (Ctrl+F) or the clipboard (Ctrl+C, Ctrl+V): for the workspaces, a new project or a new title, use the menu, the buttons or the workspace selector. On Linux, Chrome and Firefox keep Alt+1 to Alt+8 for their tabs: open the Director AI views from the **Window** menu or the summary instead.
- A key held down does not repeat a command that switches something (Space, M, N, F, U, Ctrl+S, Ctrl+G, Ctrl+D and the like). Undo, Redo, Delete and the arrows do repeat.
- On a Mac, Ctrl+K in a text field stays with the text editor; the command search is ⌘K. The / of Ctrl+/ needs Shift on some keyboard layouts: the page accepts it either way.

### Keyboard and screen readers

Every button has an accessible name, and an icon button shows its tooltip when it receives the keyboard focus, not only when the mouse hovers it. The Tab key reaches every control with a visible focus ring, including the first choice of a window that you opened with the mouse. The trim and fade handles of the timeline are mouse handles that Tab skips: use the **Cut** menu and the Inspector instead (chapters 3 and 7). A screen reader hears the progress of a generation or of an export at each 10 %, or when the step changes, and never more than once every 3 seconds.

## 17. Troubleshooting

**Generating**

- **The engine chip reads "No engine".** Your administrator has not finished the setup: an engine, a video preset assigned to you, or a cloud video model. Ask them.
- **The round button is disabled.** Read the message of the deck (**Can't generate yet**): it says what is missing and often offers the button that fixes it.
- **"Models to install for this preset: …".** The server lacks model files for that preset. Ask your administrator.
- **The Estimated cell shows "—".** No take was made yet with this preset and size, so there is no time to compare with. It fills in after a few generations.
- **"Will stream through host RAM, slower."** The model does not fit in the memory of the graphics card. The generation still runs, more slowly.
- **"GPU quota exceeded".** You used your GPU minutes for the month. Wait for next month, use a cloud model, or ask your administrator for more.
- **A warning says a shot will be made from its text only.** The shot has no first or last frame, or the engine ignores them. Add a first frame (**Use the previous shot’s last frame**, chapter 12), or accept it.
- **A take stays Queued.** Your administrator limits how many of your takes run at once; it starts when one of yours ends. If it stays Queued while nothing of yours runs, tell your administrator.
- **A take failed.** Its card explains the cause. If the graphics card ran out of memory, try a draft, a shorter shot or another engine, then **Retry**. If every take fails within seconds after such an error, ask your administrator to restart the backend.
- **I closed the page during a generation.** The takes go on. Open the project again to find them; the notifications tell you when they end.

**Final render and frame rate**

- **"Upscaler not available".** No upscaler is assigned to you. Use **Re-render at full resolution**, or ask your administrator for SeedVR2 or RTX Upscale.
- **"… run on a native backend of this instance, and none is enabled".** Your PotionUI runs takes in the cloud only, so upscalers, interpolators and the guided render are not available. Ask your administrator.
- **The export repeats frames.** No interpolator is assigned to you to conform the slow takes. Ask your administrator for Video Tools or RTX Upscale.

**Exporting**

- **"ffmpeg is missing on the server".** No video can be made until your administrator installs it. The files for other software and the subtitles still work.
- **"The server cannot write its work files".** Ask your administrator to check the storage folder of the server.
- **"No shot has a video file to export yet."** Generate or import the shots first.
- **"The export folder is full".** Delete older exports in **Previous exports**, or ask your administrator for a larger budget.
- **A shot is black or silent in the video.** Its media was removed from your library, or its sound is muted (the shot, the track V1, or another track soloed).
- **An export failed.** The card says what failed. Try again; if it fails again, give the message to your administrator.
- **A file for other software does not find its media.** The paths are those of the server: copy the media to your computer and relink them (chapter 14).

**Projects and media**

- **"Not saved — retry".** The last save failed. Click the state to try again; your changes stay in the page. If the project is too large or was refused, ask your administrator before you reload.
- **"Project reloaded: it changed elsewhere".** The project was saved from another tab or device. **File › Version history…** brings back an earlier state.
- **"This project was deleted elsewhere".** The page opened another of your projects.
- **"Media offline".** The file is no longer in your library or gallery. Import it again, or choose a take for the shot.
- **A file could not be imported.** The message gives the reason: the file is too large, its kind is not accepted, or your storage is full.

**The page**

- **The page only says "Video Producer needs a screen at least 1280 px wide."** Widen the window: the page works from 640 pixels up.
- **I cannot find the left panel or the Inspector.** In a narrow window they are drawers: open them with the first and the last buttons of the project bar.
- **The assistant does not answer or shows no card.** See chapter 10, "If it does not work".

The complete reference lists every message of the page with its cause.

## 18. Glossary

| Term | Meaning |
|---|---|
| shot | A clip of the film, made by one generation. |
| take | One generated version of a shot. |
| draft | A fast, small take to judge the motion and the framing. |
| final render | A draft enlarged (upscale) or generated again at full resolution (chapter 9). |
| label | Draft, Candidate, Rejected or Selected: how you sorted a take. The Selected take is the one the shot plays. |
| production deck | The bar at the bottom of Storyboard and Director AI, with the **Generate selection** button (chapter 8). |
| engine | What makes the takes: a video preset on your administrator's machines, or a cloud model. |
| preset | A ready-made setup of a model; your administrator installs it and assigns it to you. |
| profile | FL2VA, Ref2VA or Hybrid AV: what guides the generation (chapter 8). |
| shot editor | The window that gathers the prompt, frames, references, drafts and engine of a shot (chapter 4). |
| shot prompt | The text that describes one shot; it completes the global direction. |
| global direction | The text that guides every shot of the film. |
| bible | The cards of the recurring characters and places (chapter 4). |
| reference | A picture, video or sound that guides the generation (chapter 4). |
| reference track | An audio track whose sound goes with the generation of each shot (chapter 13). |
| seam | The cut between two neighbor shots (chapter 12). |
| seam frame | An image taken from a take and set as the first or last frame of a shot (chapter 12). |
| upscaler | A preset that enlarges a take for a final render: SeedVR2 or RTX Upscale. |
| interpolator | A preset that brings a take to the frame rate of the film: Video Tools or RTX Upscale. |
| conform | Make a version of a take at the frame rate of the film (chapter 9). |
| seed | The number that fixes the randomness of a take; the same seed gives a similar take. |
| variant | One of the takes (A, B, …) made for the same shot. |
| Prompt modified | The mark of a take made before the last edit of its shot. |
| version | A saved state of the project (chapter 5). |
| playhead | The current position on the timeline. |
| range | A part of the timeline between an in point and an out point. |
| approval | The card where you accept (**Approve**) or refuse (**Reject**) what the assistant proposes (chapter 10). |
