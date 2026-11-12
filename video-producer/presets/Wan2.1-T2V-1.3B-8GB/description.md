Generate a short video from a prompt with Wan 2.1's 1.3B text-to-video model, set up for a graphics card with **8 GB of VRAM** and **32 GB of system RAM**. It is the smallest local video model PotionUI runs: 480p clips of up to 5 seconds at 16 fps, in 832×480, 480×832, 640×480, 480×640, 640×640 or 576×720, with 30 steps and CFG 6. Count about 6 minutes for a 5-second clip.

**Text to video only.** A first or last frame given to a shot is not used.

**Files.** The 1.3B DiT (2.64 GB, fp16), the fp8 UMT5-XXL text encoder (6.27 GB) and the Wan 2.1 VAE.

**Memory.** It keeps the engine's memory settings at their defaults. With 16 GB of RAM in a container, the engine refused to start sampling: plan on 32 GB.

**Docker Desktop on Windows.** WSL 2 gives Docker half of the host's RAM by default. On a 32 GB PC, raise it in `%UserProfile%\.wslconfig` (`[wsl2]`, `memory=28GB`), then run `wsl --shutdown`.

**Licensing.** The weights are published under the Apache-2.0 license.
