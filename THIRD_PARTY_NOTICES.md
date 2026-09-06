# Third-party notices

Buckswood auto Mashup project code is GPL-3.0-only. External libraries and checkpoints retain their own licenses. They are downloaded or installed separately; this repository does not redistribute their complete source trees, binaries or model weights.

## Core audio components

| Component | Version / revision used | License and source |
| --- | --- | --- |
| AutoMashup | `c20d410f24568af23a5db948084746a5e13c8874` | [BSD-3-Clause](https://github.com/ax-le/automashup/blob/c20d410f24568af23a5db948084746a5e13c8874/LICENSE), © 2025 Axel Marmoret |
| Rubber Band | 4.0.0, `1d95888bec3ae0a17c0c4af791810d5a63f6bc35` | [GPL-2.0-or-later](https://github.com/breakfastquay/rubberband/blob/1d95888bec3ae0a17c0c4af791810d5a63f6bc35/README.md), © 2007–2024 Particular Programs Ltd |
| Demucs | 4.0.1, `htdemucs` | [MIT](https://github.com/facebookresearch/demucs/blob/main/LICENSE) |
| Beat This! | 1.1.0, `final0` checkpoint | [MIT; upstream covers code and published weights](https://github.com/CPJKU/beat_this#license) |
| MLX Audio | 0.5.1 | [MIT](LICENSES/mlx-audio-MIT.txt), from the installed release's license file |
| Kim Vocal 2 MLX conversion | `64cbfcb004e39430e5f584552c05949440ec39ce` | [MIT and original-checkpoint provenance](https://huggingface.co/mlx-community/mel-roformer-kim-vocal-2-mlx/blob/64cbfcb004e39430e5f584552c05949440ec39ce/README.md) |

The `Option` values in `studio/rubberband.py` mirror the public C interface in Rubber Band 4.0.0's `rubberband/rubberband-c.h`, © 2007–2024 Particular Programs Ltd, GPL-2.0-or-later. That notice is retained in the wrapper. The corresponding source is obtained by `scripts/build_rubberband.py`; its GPL text is in [LICENSES/RubberBand-GPL-2.0.txt](LICENSES/RubberBand-GPL-2.0.txt). The application uses the GPL licensing path for Rubber Band.

AutoMashup's key finder credits [musical-key-finder](https://github.com/jackmcarthur/musical-key-finder) and [pymusickit](https://pypi.org/project/pymusickit/). It is imported from the separately installed, pinned upstream source. The complete upstream AutoMashup license is retained in [LICENSES/AutoMashup-BSD-3-Clause.txt](LICENSES/AutoMashup-BSD-3-Clause.txt).

The RoFormer conversion's pinned model card documents the original model's move from GPL-3.0 to MIT in April 2026. Its downloaded license is retained here as [LICENSES/RoFormer-model-MIT.txt](LICENSES/RoFormer-model-MIT.txt). Model provenance and training-data terms are distinct from the license of this application's code. The implementation lineage also includes [BS-RoFormer](https://github.com/lucidrains/BS-RoFormer) and [Music-Source-Separation-Training](https://github.com/ZFTurbo/Music-Source-Separation-Training).

## Other dependencies

The pinned Python requirements and npm lockfile identify the installed packages. These include NumPy, SciPy, librosa, PyTorch/torchaudio, matplotlib, SoundFile/libsndfile, pyrubberband, FastAPI/Starlette, Uvicorn, python-multipart, MLX, huggingface-hub, React and Vite. Their installed distributions contain their respective licenses and notices. FFmpeg is an external executable supplied by the user; its licensing depends on its build. No FFmpeg binary is bundled.

Retain the relevant upstream license files if you distribute dependencies or build a binary bundle. The project license does not relicense songs, recordings, model weights or other third-party material.
