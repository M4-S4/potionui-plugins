Generate a video from a prompt with Wan 2.2's 14B text-to-video expert pair in 6 steps, set up for a graphics card with **12 GB of VRAM**. It is the Fast speed profile of the Wan 2.1 / 2.2 preset with the lightx2v Lightning LoRA pair already selected: 6 steps, CFG 1, 832×480 at 16 fps, clips of up to 5 seconds. Text to video only; for image to video, use the Wan 2.1 / 2.2 preset with its I2V models.

**Files.** The 14B high-noise and low-noise experts (fp8-scaled, 13.31 GB each), the fp8 UMT5-XXL text encoder, the Wan 2.1 VAE, and the lightx2v 4-step LoRA v1.1 pair for text to video (1.14 GB each), one LoRA per expert.

**Memory.** The number of steps does not change memory use: this preset loads the same experts as the 30-step profile, and most of each expert streams from system RAM on a 12 GB card, with about 35 GB of process memory, hence **64 GB of system RAM**. It leaves the engine's memory settings at their defaults.

**Not working on 12 GB yet.** Measured on a 12 GB card, the PotionUI process is killed by a CUDA out-of-memory error during sampling: the engine places as much of each expert on the card as fits and leaves no room for the LoRAs. With the engine told that the card has 8 GB (`POTIONUI_VRAM_CAP_GB=7.99`), the same clip finished in 5 min 36 s with a 6.1 GB engine peak. This preset is kept out of the shipped ones until the engine reserves that room.

**Licensing.** The Wan 2.2 weights and the lightx2v LoRAs are published under the Apache-2.0 license.
