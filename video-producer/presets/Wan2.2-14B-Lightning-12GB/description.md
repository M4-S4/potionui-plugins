Generate a video from a prompt with Wan 2.2's 14B text-to-video experts in 6 steps, set up for a graphics card with **12 GB of VRAM** and **64 GB of system RAM**. Clips of up to 5 seconds at 16 fps, 832×480 by default and up to about half a megapixel (960×544, 544×960, 832×624, 720×720 or 640×800), with CFG 1. Count about 3.5 minutes for a 5-second clip once the models are in memory; the first run of a session also reads 38 GB of files from disk.

**Text to video only.** In Video Producer, a shot that starts from an image (its own first frame, the last image of the previous shot, or a first and a last image) goes to the companion preset **Wan 2.2 14B Lightning I2V (12 GB)**, without changing the engine of the shot. Without that preset or one of its files, the shot runs here from its text, with a warning.

**Files.** The 14B high-noise and low-noise experts (fp8-scaled, 13.31 GB each), the fp8 UMT5-XXL text encoder, the Wan 2.1 VAE, and the lightx2v 4-step LoRA v1.1 pair for text to video (1.14 GB each).

**Memory.** Fewer steps do not lower memory use: most of each expert streams from system RAM on a 12 GB card, with about 35 GB of process memory. Larger sizes such as 1280×720 run out of memory on 12 GB, which is why the sizes stop at 960×544.

**Licensing.** The Wan 2.2 weights and the lightx2v LoRAs are published under the Apache-2.0 license.
