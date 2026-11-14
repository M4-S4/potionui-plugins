# PotionUI plugins

Plugins for [PotionUI](https://github.com/PotionUI/PotionUI), the self-hosted app for AI images and video, to install in a few clicks from its admin pages with this catalogue URL:
```text
https://raw.githubusercontent.com/M4-S4/potionui-plugins/main/plugins.json
```

## Install

You need an admin account on a PotionUI whose **Admin › Plugins** page shows the **Install from catalog** button.

1. Open **Admin › Plugins** and click **Install from catalog**.
2. Paste the catalogue URL above and click **Read catalog**.
3. Click **Install** next to the plugin you want, then **Install** in the window that asks to confirm. PotionUI downloads the release, checks its checksum and adds the plugin to the list, disabled: turn it on with the switch on its card in the list, or at the top of its page.

If its **Overview** tab then shows a **Setup** section, follow its steps, and read its documentation in **Admin › Documentation**. A plugin runs with the same rights as PotionUI: install only from a catalogue you trust.

## Plugins

| Plugin | What it does | Who uses it | Needs on the server | Version |
|---|---|---|---|---|
| [Video Producer](video-producer/README.md) | A page for making short films with AI video: write a synopsis, split it into shots, generate takes, pick the best ones, then edit, match colors, mix the sound and export the film. [User guide](video-producer/docs/user-guide.md). | Every user; an admin sets it up. | A video engine, video presets and their model files, and ffmpeg: its [administration page](video-producer/README.md) says what to prepare. | 0.6.0 |
| [Preset Editor](preset-editor/README.md) | Create, edit, check and publish presets without leaving PotionUI. | Admins only. | Nothing else. | 0.2.5 |
| [Media Converter](media-convert/README.md) | Adds four tools to the Tools menu of the Library and the History: convert an image to PNG, JPEG or WebP, a video to MP4, MOV or WebM, or a sound to WAV, MP3, FLAC, M4A or OGG, and extract the sound of a video. | Every user. | ffmpeg and ffprobe, which the PotionUI image ships. | 0.1.1 |

The README of Preset Editor and of Media Converter lists the changes of each version, newest first.

## Update

Open the catalogue again: a newer version shows **Update to** and its version number in place of **Install**.

- Read the catalogue at the same URL as the first time. PotionUI updates a plugin only from the exact address it was installed from; under any other address, even one that serves the same file, the plugin shows **Installed elsewhere** with no update.
- After an update, restart PotionUI.

If PotionUI refuses an update with the message that the new version did not start, the version you had is back in place. Then:

1. disable the plugin;
2. restart PotionUI;
3. update it;
4. enable it.

Preset Editor 0.2.4 needs these steps to reach 0.2.5, and Media Converter 0.1.0 to reach 0.1.1.

## Install by hand

Without the catalogue, unzip `<id>-<version>.zip` from the [releases page](https://github.com/M4-S4/potionui-plugins/releases) into `content/plugins/local/` of the instance (the zip holds the folder `<id>/`, with its built frontend when the plugin has one), then click **Scan for Plugins** in **Admin › Plugins** and enable it. In a Docker container the folder is `/app/content/plugins/local/<id>`. The catalogue does not update a plugin installed by hand: it lists it as **Installed elsewhere**, with the message that its folder was not installed from a catalog; remove the folder to install the plugin from the catalogue. To install from a clone of this repository instead, see [the maintainers' guide](dev/README.md#install-by-hand-from-a-clone).

## License

All three plugins are free software under the GPL-3.0 license, as each plugin's manifest declares; the text is in [LICENSE](LICENSE).

## Maintainers

How this repository is laid out, tested and released, and how Video Producer comes from the M4-S4/PotionUI fork: [dev/README.md](dev/README.md).
