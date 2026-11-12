Generate a video from a prompt, or from a start image, with Wan 2.2's 5B TI2V model, set up for a graphics card with **8 GB of VRAM** and **32 GB of system RAM**. Clips of up to 5 seconds at 24 fps, in 832×480, 480×832, 640×640 or 576×704, with 30 steps and CFG 5. Count about 5 minutes for a 5-second clip.

**Start images.** A shot with a first frame, or that starts from the last image of the previous shot, runs image to video. The model has no first-and-last-frame mode, so a last frame is not used.

**Files.** The 5B DiT (9.31 GB, fp16), the fp8 UMT5-XXL text encoder (6.27 GB) and the Wan 2.2 VAE (1.31 GB, not interchangeable with the Wan 2.1 VAE).

**Memory.** The engine converts the DiT to fp8 while loading, so that it fits on an 8 GB card (Admin › Backends › Optimizations: fp8 quantization `auto`, the default). The fp16 file is read whole into system RAM first.

**Why no 720p.** At the model's native 1280×704, decoding needs far more than 8 GB. For 720p, use the Wan 2.1 / 2.2 preset with the 5B checkpoint on a larger card.

**Sampling shift.** The engine samples every Wan model with a shift of 8.0; the official setting for the 5B is 5.0. The form does not expose it.

**Docker Desktop on Windows.** WSL 2 gives Docker half of the host's RAM by default. On a 32 GB PC, raise it in `%UserProfile%\.wslconfig` (`[wsl2]`, `memory=28GB`), then run `wsl --shutdown`.

**Licensing.** The weights are published under the Apache-2.0 license.
