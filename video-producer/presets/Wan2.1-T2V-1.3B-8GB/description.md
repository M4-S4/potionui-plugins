Generate a short video from a prompt with Wan 2.1's 1.3B text-to-video model, set up for a graphics card with **8 GB of VRAM** and **32 GB of system RAM**. It is the smallest local video model PotionUI runs: 480p clips of up to 5 seconds at 16 fps (832×480, 480×832, 640×480, 480×640, 640×640 or 576×720), 30 steps, CFG 6. Text to video only: a shot's first or last frame is not used.

**Files.** The 1.3B DiT (2.64 GB, fp16), the fp8 UMT5-XXL text encoder (6.27 GB) and the Wan 2.1 VAE. The model pickers recommend only these files.

**Memory.** The text encoder runs first, then leaves the card before sampling. This preset leaves the engine's memory settings at their defaults (Admin → Backends: text encoder placement `auto`, fp8 quantization `auto`). Measured on a 12 GB card capped to 8 GB (`POTIONUI_VRAM_CAP_GB=7.99`, `gpu_max_vram` 6) in a container limited to 32 GB, then 29 GB, of RAM: a 5-second 832×480 clip took about 5 min 40 s, with a peak of 5.2 GB of VRAM allocated by the engine and 10.6 GB of process memory outside the file cache. In a container limited to 16 GB the engine refused to start sampling: it reads the free RAM of the container including the file cache of the model files, and did not see the 2.6 GB it wanted for streaming plus its 2 GB margin. A machine with 16 GB of RAM outside a container was not measured.

**Docker Desktop on Windows.** WSL 2 gives Docker half of the host's RAM by default. On a 32 GB PC, raise it in `%UserProfile%\.wslconfig` (`[wsl2]`, `memory=28GB`), then run `wsl --shutdown`.

**Licensing.** The weights are published under the Apache-2.0 license.
