Generate a video from a starting image, or from a first and a last image, with Wan 2.2's 14B image-to-video expert pair in 4 steps, set up for a graphics card with **12 GB of VRAM**. It is the image-to-video companion of **Wan 2.2 14B Lightning (12 GB)**: the Fast speed profile of the Wan 2.1 / 2.2 preset with the lightx2v 4-step image-to-video LoRA pair already selected, 4 steps, CFG 1, 832×480 at 16 fps, clips of up to 5 seconds, in the same sizes of up to about half a megapixel (960×544, 544×960, 832×624, 720×720 or 640×800 at most). It has no text-to-video mode.

**In Video Producer.** You do not need to pick it: a shot whose engine is Wan 2.2 14B Lightning (12 GB) and that starts from an image (its own first frame, the last image of the previous shot, or a first and a last image) is generated with this preset, and its takes name it. A shot without an image whose engine is this preset goes back to Wan 2.2 14B Lightning (12 GB).

**Files.** The 14B image-to-video high-noise and low-noise experts (fp8-scaled, 13.31 GB each), the fp8 UMT5-XXL text encoder, the Wan 2.1 VAE, and the lightx2v 4-step LoRA v1 pair for image to video (1.14 GB each), one LoRA per expert. The text encoder and the VAE are the files of Wan 2.2 14B Lightning (12 GB), and the experts are those of the core Wan 2.1 / 2.2 preset: the recipe downloads only what is not on the disk yet.

**Memory.** It loads experts of the same size as the text-to-video preset, so plan on the same **64 GB of system RAM**. It leaves the engine's memory settings at their defaults.

**Measured on 12 GB** (9 November 2026, 832×480, 5 seconds, LoRA pair and experts on disk): a shot from the last image of the previous one took 162 s and a first-and-last-frame shot 135 s in 4 steps, with an engine peak of 6.6 GB and 5.4 GB. The same shots in 6 steps took 209 s and 189 s for frames the eye does not tell apart, with slightly wider motion. The sizes stop at 960×544 like those of the text-to-video preset until a take is measured above 832×480.

**Licensing.** The Wan 2.2 weights and the lightx2v LoRAs are published under the Apache-2.0 license.
