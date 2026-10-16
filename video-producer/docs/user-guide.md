# Video Producer: user guide

Français : [Video Producer : guide utilisateur](/docs?doc=plugin/video-producer/user-guide.fr) (fichier `docs/user-guide.fr.md`).

This guide explains how to make a short film with Video Producer. Interface labels are written in **bold**. A chapter about something that does not exist yet ends with "Available from step N". The administrator guide is a separate page that only admins see.

## 1. What Video Producer is

Video Producer is a PotionUI plugin for audiovisual editing, AI sequence generation, art direction, sound creation and 3D scene preparation, all in one page. You write a synopsis, split it into shots, generate quick draft takes, choose the best one, turn it into a final, then cut, match colors, mix sound and deliver. It opens from the **Video Producer** entry in the sidebar.

Before you start:

- An admin has to prepare at least one engine (this machine, a studio server or a cloud model) and at least one video preset assigned to you. If the Production bar shows no engine, see chapter 16.
- Your admin also sets the draft resolution and may limit the GPU minutes you can use per month.
- The model MiniMax-H3 comes with a license that excludes use, and anything generated with it, in the European Union, the United Kingdom, the United States and South Korea without an individual authorization from MiniMax, and that asks a commercial product to display "MiniMax H3" prominently. Ask your admin before you use it.

The interface is in English by default and also exists in French (chapter 13).

## 2. The path in eight steps

1. **Create a project.** **File › New project…** (or **File › Open…** for an existing one). In **Project properties…** you set the name, the format (16:9, 2.39:1, 9:16, 1:1 or 4:5), the resolution (720p, 1080p or 4K) and the frame rate (24, 25 or 30 fps). Result: an empty project that is saved as you work.
2. **Set the global direction.** In the **Director IA** workspace, tab **Direction**: world and intent, characters and identity, cinematography, palette and lighting, pacing and continuity. Result: a text that guides every generation.
3. **Add references.** In **Director IA**, tab **References**: identities, 3D sets and motion guides. Result: what must stay the same from one shot to the next.
4. **Split the film into shots.** In the **Storyboard** workspace: write the synopsis, click **Propose a split**, keep the shots you want and adjust their shot prompts. Result: a row of shot cards.
5. **Generate drafts.** In the Production bar, quality **Draft**, then **Generate selection** (⌘ G). The estimate shows GPU time and quota. Result: draft takes A, B, and so on.
6. **Choose a take and make it final.** In the Inspector, tab **Takes**: compare, click **Use**, then **Final** on the best take. Result: the shot moves from Draft to Final.
7. **Cut, match and mix.** Fades on the clips, color match in the Inspector tab **Color**, the console in **Mix**. Result: a finished sequence.
8. **Deliver.** **File › Export video…**, **Export to other software…** or **Export subtitles…**. Result: files you can download.

Available from step 2: the interface of all eight steps. From step 3: saved projects. From step 4: drafts and finals. From step 6: delivery.

## 3. The screen

The page has five levels, from the widest to the most local:

- **Menu bar.** Ten menus, in this order: **Video Producer**, **File**, **Edit**, **Cut**, **Shot**, **Production**, **Audio**, **View**, **Window**, **Help**. The **Video Producer** menu holds About, **Preferences…**, **Keyboard shortcuts** and **Search commands…**.
- **Project bar.** The project name and its save state, the workspace selector (**Media**, **Director IA**, **Storyboard**, **3D scene**, **Mix**), **Import**, **Export**, **Assistant** and the buttons that show or hide the side panel and the Inspector.
- **Production bar.** It targets what to generate and holds the only main button of the page, **Generate selection** (chapter 6).
- **Area headers and the timeline toolbar.** A title and counters on the left, small icons on the right.
- **Content.** Small buttons that appear when you hover or select.

A rule to remember: every other entry point (Storyboard, side panel, Director IA) only targets what to generate; the Production bar is the one that acts. Menus show **…** only when the command opens a window that asks for something. The status bar at the bottom shows the number of shots and the duration, the active tool, the selection, the range, the number of direction points to check, the generation queue, snapping, your **GPU quota** and a reminder of the language (`EN` or `FR`).

Available from step 2.

## 4. Workspaces

Each workspace changes the left panel and the center. The Inspector on the right follows your selection in all of them.

### Media

The project library and the **PotionUI gallery** in one panel. Filter with the collection pills (**All**, **PotionUI gallery**, **Generated** and your own), search by name without worrying about accents, double-click to preview, drag to the timeline. For a selected item, **Preview**, **Add to cut**, and, for images and videos, **Use as frame at playhead**.

### Director IA

Three tabs:

- **Direction.** Shows what guides the generation: the global direction, the shot prompts of the range, the references and controls. Below, **Points to check**, the **Project H3 profile** (FL2VA, Ref2VA or Hybrid AV, chapter 9) and the **Global direction** itself, in five fields, with a counter that stops at 4000 characters.
- **References.** Three families, **Images and identity**, **3D sets** and **Motion guides**. A reference is global (it goes with every generation) or applies to a range only; **Attach to range** sets the second. **Reference** adds one.
- **Results.** The takes of each shot, **Compare**, **Retake**, **Use**, the generation queue and **Assemble chosen takes**.

### Storyboard

On the left: the **Synopsis** (one sentence becomes one shot), **Propose a split** and the proposed split, where you tick the shots to keep and click **Add N shots at the end**, then **To produce**, with the time left for drafts and for finals, and **Continuity**. In the center: one card per shot, in order, with its stage (**Source**, **To generate**, **Draft** or **Final**), its number of takes and its shot prompt. Drag a card to move it. The button of a card follows its stage: **Generate**, **Make final**, **View takes** or **Regenerate**.

### 3D scene

Scenes, **3D shots on the timeline**, **Preset paths** (Orbit, Dolly in, Rise), the camera and its keyframes in the Inspector, and **Outputs for generation**: **Capture a frame** and **Generate the control video**. This workspace is partly simulated: see chapter 15.

### Mix

**Project sounds**, the **Sound design workshop**, the **Roles** (Dialogue, Music, Ambience, SFX) and the mixing console: faders, **M** and **S**, pan, equalizer, compressor, filter, reverb and delay sends, meters and an automation mode. The console plays your real audio files. The workshop and the automation curves are simulated: see chapter 15.

Available from step 2. Your own media and saved projects: from step 3.

## 5. Inspector

The Inspector follows the selection. For a shot it has three tabs:

- **Shot.** The name, the stage, the duration and the source, the fades, and the mark **Favorite** or **Rejected**.
- **Takes.** The takes of the shot (chapter 7).
- **Color.** The luminance scope, the match with the previous shot, presets and fine settings (chapter 10).

Other items have their own panel: audio clip, title, shot prompt, reference frame, Control video, 3D shot, marker, reference and console strip. In the **3D scene** workspace with a 3D shot selected, the Inspector shows the **Camera**. With nothing selected it shows the project and a **Project properties…** button.

Available from step 2.

## 6. Production bar and estimate

The Production bar reads like a sentence: a target (**Shot**, **Range** or **Sequence**), the range and what it holds, a quality (**Draft** or **Final**), an output mode, an engine, the **Advanced workshop**, then the estimate, the queue and **Generate selection**.

- The output mode **AI generation** is the real one. **3D render** and **3D render + AI** are simulated (chapter 15).
- The engine pop-up lists what your admin enabled: **This machine**, **Studio server** and cloud models.
- The **Advanced workshop** has three steps: **Sources and guides**, **Engine and Hybrid builder** and **Sound and delivery**.

The estimate gives the GPU time, the memory and what is left of your quota:

- The time comes from your own past generations on this machine with the same preset, engine and resolution. It shows "—" when there is none yet.
- The memory is an estimate from the size of the model files, never a guarantee.
- The quota is your monthly **Video Producer GPU minutes**. A cloud engine does not use it. Only admins see the cost of a cloud generation.

What blocks **Generate selection**:

- no valid range;
- neither a global direction nor a shot prompt in the range;
- an empty shot prompt in the range;
- the FL2VA profile without a start or an end frame;
- a spent quota.

What only warns, without blocking: a memory estimate above what the engine has. The warning reads "will stream through host RAM, slower", and the generation goes on.

While a generation runs the bar shows the step and the progress, with **Cancel**.

Available from step 4.

## 7. Takes and final

A take is one generated video for one shot.

- Drafts are made at the resolution your admin chose (832×480 unless changed). The frame rate of a take is set by the preset (Wan 16 fps, MiniMax-H3 24 fps). The timeline and the exports use the frame rate of the project.
- Several variants are made per shot: A, B, and so on. Click the eye icon to preview one in the viewer, use **Compare** on two takes to see them side by side.
- **Use** makes a take the one that the shot plays; it then shows **Used**. **Retake** flags a take you want to redo. **Instructions used** shows the exact instructions behind a take.
- **Final** on a draft take makes it final. By default the take is upscaled with SeedVR2, to 720p, 1080p, 1440p or 2160p. **Re-render**, the secondary action, generates the shot again at the highest resolution of the preset, with the same seed. The new take says which one it comes from ("from A").

Available from step 4.

## 8. Assistant

The **Assistant** button, **Window › PotionUI assistant** and ⌘ J open the PotionUI chat in a window over the page, in the **Video Producer** mode. The assistant can:

- write the prompt of the selected shot;
- fix the contradictions between the global direction and the shot prompts;
- split your synopsis into shots;
- check the continuity between shots.

Every change to the project asks for your approval before it is applied. The assistant knows the workspace you are in, your selection, the playhead, the range, the global direction, the synopsis and the state of the production. It needs your admin to have set up a language model.

Available from step 5.

## 9. Prompts: library and composer

The window **Prompt library & assistant** opens from **Window › Prompt library**, or from the **Library & assistant** buttons next to a text. It writes into a target: one of the five fields of the global direction, or a shot prompt.

- **Library.** Five libraries, **Built-in**, **Personal**, **Project**, **Favorites** and **History**, and nine categories (Cinema, Camera, Lighting, Cinematic styles, Dialogue, Photography, Sound, Continuity, Avoid). A template can have variables, such as the subject or the place, that you fill in before inserting it.
- **Composer.** Builds a prompt from four parts, **Camera movement**, **Lighting**, **Cinematic style** and **Dialogue or acting intent**, for the H3 profile of the project.
- **Append** adds to the existing text; **Replace** replaces it.

The three H3 profiles and what each one asks for on the range:

| Profile | Meaning | It asks for |
|---|---|---|
| FL2VA | Continuity between the start and end images. | Start and end frames on the range. |
| Ref2VA | Keep the identity of the references during the action. | An identity reference (a character, an object). With MiniMax-H3 the generation really follows the references. |
| Hybrid AV | The soundtrack, the rhythm and the dialogue guide the picture. | An audio track on the range (dialogue or music). |

When a Control video is present, the motion comes from the guide.

Available from step 2.

## 10. Color and continuity

An alert appears only when two neighbor shots do not match: "“Shot” is lighter, darker, warmer or cooler than the previous shot". **Match** fixes it in one click by adjusting exposure and temperature to the previous shot. The measure is made on the real thumbnails of the takes. The **Color** tab also has the luminance scope, six presets (Original, Golden light, Cold morning, 35 mm film, Blue night, Soft) and fine settings (**Exposure**, **Contrast**, **Saturation**, **Temperature**), with **Reset** and **Apply to all shots**.

The identity percentage that the prototype showed between two shots is simulated (chapter 15). Color is real.

Available from step 6.

## 11. Audio and subtitles

Audio lives in tracks, each with a role: Dialogue, Music, Ambience or SFX. **Audio › Add audio track** and **Audio › Import audio file…** bring sounds in; **Audio › Mixing console** shows the console. **Voice and dialogue…** and the sound design commands open the workshop, which is simulated (chapter 15). The text of a dialogue is real: it feeds the subtitles, together with the titles of the timeline.

Available from step 3.

## 12. Exports

**File › Export video…** opens **Export and share**, with three tabs:

- **Video.** Pick a format, a resolution and the extent (the whole sequence or the range). H.264 MP4 and VP9 WebM files are assembled for real. ProRes 422, H.265 and audio stems are marked simulated.
- **To other software.** Final Cut Pro (`.fcpxml`), OpenTimelineIO (`.otio`) and EDL CMX 3600 (`.edl`). They are real files.
- **Subtitles.** An SRT file built from the dialogue text and the titles.

Before the export, the window warns about shots that are not final yet, takes flagged **Retake** and direction contradictions that are not solved. Exports are written to your PotionUI storage, in a `video_producer/exports/` folder, and you download them from the page. Your admin sets a size budget for that folder per user.

Available from step 6.

## 13. Language

Choose **English** or **Français** in **Video Producer › Preferences…**, or click the `EN` or `FR` reminder in the status bar. The change is immediate and is saved for you alone. It translates the interface and the messages; your own texts (synopsis, direction, prompts, names you typed) are never translated.

Available from step 2.

## 14. Keyboard shortcuts

⌘ is Command on a Mac and Ctrl elsewhere. **Search commands…** (⌘ K) finds any command, and **Keyboard shortcuts** lists them. This table lists the shortcuts that work; a shortcut shown in a menu but missing here may not be active yet.

| Shortcut | Action |
|---|---|
| ⌘ K | Search commands |
| Esc | Close the palette, a window, the assistant or a menu; otherwise clear the selection |
| ⌘ Z, ⇧ ⌘ Z | Undo, redo |
| ⌘ S | Save |
| ⌘ B | Split at playhead |
| ⌘ D | Duplicate |
| ⌘ G | Generate selection |
| ⌘ E, ⇧ ⌘ E | Export video…, Export to other software… |
| ⌘ I | Import files… |
| ⌘ J | PotionUI assistant |
| ⌃ ⌘ 1 | Side panel |
| Space | Play, pause |
| A, R, B | Select tool, Range select tool, Blade tool |
| M | Add marker |
| I, O | Set in point, set out point |
| N | Snapping |
| ⌫ | Delete |
| ← → | One frame back or forward (one second with Shift) |
| Home | Go to the start |

Available from step 2. The table is confirmed against the plugin at the final step.

## 15. What is simulated

Some parts keep their interface but do not do the real thing yet. They carry a gray dashed badge, **Simulated**, never a yellow one: yellow is kept for real points to check. **Help › Simulated features** opens the list.

**Real in Video Producer**

| What | How it works |
|---|---|
| **Generation.** | Takes are real video files made by the engine you pick (this machine, a studio server or a cloud model). Progress and errors come from the engine. The estimate shows GPU time (from your own past runs here, "—" when there is none), memory, your monthly quota and, for admins only, the cloud cost. |
| **Finishing a take.** | **Final** upscales the chosen take with SeedVR2 by default. **Re-render** (secondary) generates it again at the highest resolution of the preset with the same seed. |
| **Assistant.** | The PotionUI chat in Video Producer mode writes shot prompts, fixes conflicts with the global direction, splits a synopsis into shots and checks continuity. You approve each change before it touches the project. |
| **Reference-guided generation.** | With MiniMax-H3, the Ref2VA profile really conditions the generation on your references. |
| **Media and projects.** | Import goes through PotionUI's pickers, the gallery shows your own media, projects are saved, thumbnails and video playback are the real files. |
| **Color.** | Color matching is measured on the real thumbnails. |
| **Mixing.** | The console plays your real audio files: faders, mute and solo, pan, equalizer, compressor, sends and meters. |
| **Export.** | H.264 MP4 and VP9 WebM videos assembled with ffmpeg, Final Cut Pro XML, OpenTimelineIO, EDL and SRT subtitles are real files. |
| **Subtitles.** | The text of the dialogues and the titles feed the SRT file. |

**Still simulated, and why**

| What | Why |
|---|---|
| **Engine settings with no counterpart in the chosen preset**: `hybrid`, `profiles`, `consistency`, `lockIdentity`, `motionPriority`, `offset`, `followCut`, `guidance`, `overlap`, `windowLen`, `loras`, `post.*`, `audioDriver`, `lipSync`, `naming`, `autoInsert`, `quality`. | A preset only exposes the controls it declares; MiniMax-H3, for example, has no guidance and no negative prompt. They stay visible, grayed and marked simulated. |
| **Identity score between shots.** | Color matching is measured on the real frames; the similarity percentage between two shots is not, because no identity measure is available to plugins. |
| **Lip sync and generated voices.** | Voice, character and timbre settings do not produce speech yet, and lip sync has no separate step (MiniMax-H3 makes picture and sound in one pass). The dialogue text does feed the subtitles for real. |
| **Sound design workshop beyond voice**: Ambience, Foley, Texture, Impact, Music. | No preset prepares these sounds yet, so the workshop only simulates the preparation. |
| **ProRes, H.265 and audio stems.** | PotionUI's video converter writes H.264 MP4 or VP9 WebM only, and no per-role audio render exists. |
| **Automation curves of the console.** | The Auto button only switches a mode; no curve is recorded. |
| **3D scene.** | The camera, keyframes and trajectories work, but the scene stays a 2D point preview; Gaussian Splat files are referenced and not loaded; the guide video is not rendered. |
| **3D capture and imported Control video.** | They keep the prototype behavior: the capture is not rendered from the 3D scene and the imported Control video is not sent to an engine. |
| **Production modes 3D render and 3D render + AI.** | They depend on the guide video of the 3D scene, which is not rendered. |

## 16. Troubleshooting

- **The Production bar shows no engine.** Your admin has not finished the setup: an engine, a video preset assigned to you. Ask them to open Admin → Plugins → Video Producer.
- **The estimate shows "—" for the time.** Nothing has been measured yet for this preset, engine and resolution on this machine. It fills in after a few generations.
- **"Will stream through host RAM, slower".** The memory estimate is above what the engine has. The generation is not blocked. If the server lacks free memory for it, the engine refuses to start and the take fails with an error.
- **The quota is spent.** **Generate selection** is refused until the next month or until your admin raises the limit of your plan. Running generations are not stopped.
- **Generate selection is disabled.** Read the message in the bar: no range, no direction and no shot prompt, an empty prompt, the FL2VA profile without a start or end frame, or the quota.
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
