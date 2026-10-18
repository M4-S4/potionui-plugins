Generate a video from a prompt with Wan 2.2's 5B TI2V model, set up for a graphics card with **8 GB of VRAM** and **32 GB of system RAM**. Clips of up to 5 seconds at 24 fps (121 frames), the frame rate the model was trained at, in 832×480 or 480×832, 30 steps, CFG 5. Text to video only: PotionUI does not run this model's image conditioning, so a shot's first or last frame is not used.

**Files.** The 5B DiT (9.31 GB, fp16), the fp8 UMT5-XXL text encoder (6.27 GB) and the Wan 2.2 VAE (1.31 GB, 48 channels, not interchangeable with the Wan 2.1 VAE). The model pickers recommend only these files.

**Memory.** In fp16 the DiT does not fit on an 8 GB card, but it does in fp8: the engine converts it while loading (Admin → Backends → Optimizations: fp8 quantization `auto`, the default). The fp16 file is read whole into system RAM first. Measured on a 12 GB card capped to 8 GB (`POTIONUI_VRAM_CAP_GB=7.99`, `gpu_max_vram` 6) in a container limited to 32 GB, then 29 GB, of RAM: a 5-second 832×480 clip took about 4 min 40 s, with a peak of 5.5 GB of VRAM allocated by the engine and 18.6 GB of process memory outside the file cache.

**Why no 720p.** The model's native 1280×704 was tried with the same 8 GB cap: the 30 steps finished in about 26 minutes, but decoding with the Wan 2.2 VAE needed far more than 8 GB (11.9 GB on the card and 15.7 GB of shared memory) and had not finished after another 35 minutes. This preset therefore only offers 480p. For 720p, use the Wan 2.1 / 2.2 preset with the 5B checkpoint on a larger card.

**Sampling shift.** The engine samples every Wan model with a shift of 8.0; the official setting for the 5B is 5.0. The form does not expose the shift.

**Docker Desktop on Windows.** WSL 2 gives Docker half of the host's RAM by default. On a 32 GB PC, raise it in `%UserProfile%\.wslconfig` (`[wsl2]`, `memory=28GB`), then run `wsl --shutdown`.

**Licensing.** The weights are published under the Apache-2.0 license.
