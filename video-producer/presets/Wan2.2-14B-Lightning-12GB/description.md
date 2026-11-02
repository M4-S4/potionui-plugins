Generate a video from a prompt with Wan 2.2's 14B text-to-video expert pair in 6 steps, set up for a graphics card with **12 GB of VRAM**. It is the Fast speed profile of the Wan 2.1 / 2.2 preset with the lightx2v Lightning LoRA pair already selected: 6 steps, CFG 1, 832×480 at 16 fps, clips of up to 5 seconds, in sizes of up to about half a megapixel (960×544, 544×960, 832×624, 720×720 or 640×800 at most). Text to video only; for image to video, use the Wan 2.1 / 2.2 preset with its I2V models.

**Files.** The 14B high-noise and low-noise experts (fp8-scaled, 13.31 GB each), the fp8 UMT5-XXL text encoder, the Wan 2.1 VAE, and the lightx2v 4-step LoRA v1.1 pair for text to video (1.14 GB each), one LoRA per expert.

**Memory.** The number of steps does not change memory use: this preset loads the same experts as the 30-step profile, and most of each expert streams from system RAM on a 12 GB card, with about 35 GB of process memory, hence **64 GB of system RAM**. It leaves the engine's memory settings at their defaults.

**Measured on 12 GB.** On an RTX 4070 Ti with 12 GB, the whole card left to the engine and its default settings, a 5-second clip at 832×480 took 3 min 24 s once the models were in memory, with an 8.1 GB engine peak and 34.7 GB of process memory. The first run of a session also reads the 38 GB of files from disk. Larger sizes do not fit: at 1280×720 a 5-second clip ran out of memory at its first step, and at 1488×624 a 3-second clip finished its steps but ran out of memory while decoding (October 2026). Both times the engine had to be restarted. This preset therefore offers no size above 960×544.

**Licensing.** The Wan 2.2 weights and the lightx2v LoRAs are published under the Apache-2.0 license.
