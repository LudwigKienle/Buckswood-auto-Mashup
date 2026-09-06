# Quality methods and limitations

The largest quality gains usually come from choosing compatible source material, retaining complete vocal phrases, and avoiding extreme tempo changes. A more complex separator alone cannot fix an unsuitable arrangement.

## Separation

The optional HQ pipeline separates vocals with a pinned Mel-Band RoFormer MLX checkpoint. It then sends the residual instrumental through Demucs for drums and bass; the remaining accompaniment is reconstructed by subtraction. This keeps the separated parts consistent with the original mixture. The base Demucs stems remain available for comparison.

The MLX worker uses reflected edge context and normalized Hann overlap-add, then rejects missing model weights, unexpected shapes and non-finite output. HQ stems become selectable only after successful completion. These checks protect signal integrity; they do not prove cleaner vocals. Reverberation, doubled vocals, distortion and shared harmonics can still cause leakage or lost consonants.

The architecture follows [Mel-Band RoFormer](https://arxiv.org/abs/2310.01809) through the [MLX Audio implementation](https://github.com/Blaizzy/mlx-audio/tree/main/mlx_audio/sts/models/mel_roformer). The checkpoint is documented in [its model card](https://huggingface.co/mlx-community/mel-roformer-kim-vocal-2-mlx). Numerical agreement with a model's original implementation is not a separation-quality score on your songs.

## Arrangement continuity

[Beat This!](https://github.com/CPJKU/beat_this) supplies observed bar boundaries. The planner searches for long phrases using vocal activity, boundary costs and time-varying chroma similarity in both vocal/backing directions. It compares 8- and 16-bar themes, preferring longer phrases unless their boundary/harmony scores or prominent internal vocal-timbre changes favor a shorter candidate. Timbre novelty uses bar-averaged MFCC features and activity over neighboring bars; it does not identify speakers or understand lyrics. It holds the backing stable at the first singer handover and returns to an earlier theme later in the arrangement.

Adjacent sections that use a continuous passage of the same vocal or backing source are stretched as a single run, then split for mixing. A complete backing is combined before stretching; in hybrid arrangements bass and other instruments are combined before stretching. This avoids destroying cancellation between those separated parts with different stretch passes. A complete backing is pitch-shifted as a whole, including its drums; the separate drum component in a hybrid arrangement remains unpitched. This avoids a fresh vocal-processing boundary whenever the instrumental changes. Transitions use actual outgoing source context rather than fabricated repeated syllables.

The analysis does not understand lyric meaning, reliably label verse/chorus structure, or identify every chord. Bar detection can be wrong, and a chroma match can still sound musically unsuitable. Review the proposed entries and use the manual controls. Larger pitch shifts receive a stronger planning penalty beyond two semitones, so a small chroma-score improvement alone is less likely to justify a markedly altered voice. This is a quality heuristic; manual pitch controls remain available.

## Timing and mixing

[Rubber Band](https://github.com/breakfastquay/rubberband) processes time and pitch together, with R3 for vocals/melodic parts, R2 for drums, formant preservation for vocals and observed bar anchors where available. A balanced tempo proposal distributes the relative speed change across the two songs. It cannot recreate a natural performance when the required change is large.

Fixed pitch shifts enable Rubber Band’s high-quality pitch option, following its [integration notes](https://breakfastquay.com/rubberband/integration.html). Source excerpts include 120 ms of real preceding context, cropped after processing. Observed grids within 12 ms of a straight target grid use a constant ratio instead of following timestamp quantization. This tolerance is a heuristic.

Vocal level is referenced to active passages. A vocal high-pass and dynamic midrange reduction in the backing run once across the assembled song so their state survives section boundaries. The stereo-linked control has a 15 ms attack and 180 ms release. Midrange extraction uses [SciPy’s forward/backward SOS filtering](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.sosfiltfilt.html), so subtracting the band does not introduce the phase rotation of a one-way filter. New imports decode to float WAV, avoiding an unnecessary 16-bit quantization step. WAV/MP3 mastering uses a two-pass loudness process. Unmastered float vocal and instrumental buses are available for manual finishing.

## Listening checks

Compare both separation versions at the same source timestamp and matched vocal loudness. Listen for consonants, breaths, reverb tails, cymbal leakage and changes in the stereo image. Then check the same passage inside the arrangement: solo cleanliness does not automatically predict the best mix.

The local A/B helper accepts your own library ID:

```sh
python -m scripts.compare_separation YOUR_TRACK_ID --start 30 --seconds 16 --label vocals
```

Run it with the installed Python runtime from the README. Both separation versions must already exist. It exports matched excerpts and a combined comparison into the local data folder's `quality-ab` directory.

The automated tests check DSP invariants and planning behavior with synthetic fixtures. No benchmark improvement or professional production quality is claimed. Future work should use licensed evaluation stems and blind listening comparisons, especially for lyric continuity, local chord compatibility and rhythm-aware placement of vocals.
