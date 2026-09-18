# Quality methods and limitations

The largest quality gains usually come from choosing compatible source material, retaining complete vocal phrases, and avoiding extreme tempo changes. A more complex separator alone cannot fix an unsuitable arrangement.

## Separation

The optional HQ pipeline separates vocals with a pinned Mel-Band RoFormer MLX checkpoint. It then sends the residual instrumental through Demucs for drums and bass; the remaining accompaniment is reconstructed by subtraction. This keeps the separated parts consistent with the original mixture. The base Demucs stems remain available for comparison.

The MLX worker uses reflected edge context and normalized Hann overlap-add, then rejects missing model weights, unexpected shapes and non-finite output. HQ stems become selectable only after successful completion. These checks protect signal integrity; they do not prove cleaner vocals. Reverberation, doubled vocals, distortion and shared harmonics can still cause leakage or lost consonants.

The architecture follows [Mel-Band RoFormer](https://arxiv.org/abs/2310.01809) through the [MLX Audio implementation](https://github.com/Blaizzy/mlx-audio/tree/main/mlx_audio/sts/models/mel_roformer). The checkpoint is documented in [its model card](https://huggingface.co/mlx-community/mel-roformer-kim-vocal-2-mlx). Numerical agreement with a model's original implementation is not a separation-quality score on your songs.

## Arrangement continuity

The musical planner compares continuous 8-, 16-, 24- and 32-bar themes. Around three minutes is a soft duration preference evaluated at the chosen output tempo; harmony, vocal boundaries and structural changes keep their existing penalties. It adds no loops or filler to reach a timestamp, and can keep a shorter arrangement when longer source passages fit poorly. A 24-bar response changes backing after 8 bars, then continues for 16. The arrangement displays its estimated total duration before rendering. The preview remains limited to the actual first 32 bars.

V6 treats the opening as part of the arrangement. It favors a connected 4- or 8-bar lead-in to the first backing passage and compares the available lead-ins for moderate initial rhythm energy, build and large internal energy jumps. The source may be later in a song: the aim is to introduce the chosen motif, not simply concatenate both originals from zero. If no preceding bars fit, a shorter instrumental preview of the coming motif is used. Rebuilding an intro preserves the subsequent sections and honors explicit source-BPM overrides.

During an intro, bass and drums begin at reduced levels and rise smoothly to unity before the next section. This is applied to the original stems before one combined time/pitch pass, keeping the following backing intact. A zero-phase low-pass blend opens the upper spectrum. This is a production heuristic, not a guarantee of a compelling composition or artifact-free stem separation. The first-32-bar preview now retains the actual opening and arrangement order.

[Beat This!](https://github.com/CPJKU/beat_this) supplies observed bar boundaries. The planner searches for long phrases using vocal activity, boundary costs and time-varying chroma similarity in both vocal/backing directions. It compares 8- and 16-bar themes, preferring longer phrases unless their boundary/harmony scores or prominent internal vocal-timbre changes favor a shorter candidate. Timbre novelty uses bar-averaged MFCC features and activity over neighboring bars; it does not identify speakers or understand lyrics. It holds the backing stable at the first singer handover and returns to an earlier theme later in the arrangement.

Adjacent sections that use a continuous passage of the same vocal or backing source are stretched as a single run, then split for mixing. A complete backing is combined before stretching; in hybrid arrangements bass and other instruments are combined before stretching. This avoids destroying cancellation between those separated parts with different stretch passes. A complete backing is pitch-shifted as a whole, including its drums; the separate drum component in a hybrid arrangement remains unpitched. This avoids a fresh vocal-processing boundary whenever the instrumental changes. Transitions use actual outgoing source context rather than fabricated repeated syllables.

The analysis does not understand lyric meaning, reliably label verse/chorus structure, or identify every chord. Bar detection can be wrong, and a chroma match can still sound musically unsuitable. Review the proposed entries and use the manual controls. Larger pitch shifts receive a stronger planning penalty beyond two semitones, so a small chroma-score improvement alone is less likely to justify a markedly altered voice. This is a quality heuristic; manual pitch controls remain available.

## Timing and mixing

V5 looks for vocal pauses of at least 120 ms below a relative RMS threshold (12% of the vocal reference level), rather than treating every short consonant gap as a phrase boundary. Planning considers both nearby bounded phrases and the available space between singers. Energy-based pause detection follows the general principle documented in [librosa's non-silent interval analysis](https://librosa.org/doc/0.11.0/generated/librosa.effects.split.html), with our own minimum-gap and edit-handle rules. It does not recognize sentences, words or breaths semantically. Quiet singing and separator leakage can still confuse it.

The renderer reads up to roughly two beats of real vocal context (capped at 1.6 seconds) before and after each continuous vocal run. It preserves a complete bounded pickup or release only when the surrounding vocal timeline is quiet. Context travels through the same time/pitch pass as the phrase; the bars and output duration do not move. It never copies a later phrase across an existing pause or fabricates a repeated word. If no pause is found or another singer occupies the handle, it skips the full extension and uses a 6 ms edge fade. An unbounded outgoing sustain may retain the earlier 180 ms fade into silence; this is recorded as a short release, not as a recovered word. Continuous runs bypass these edits. Manual vocal offsets bypass automatic handles; the user can also disable phrase protection for A/B comparison. Individual decisions are recorded in the export's `processing.vocal_edits` field.

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

## V7: optional SheetSage2 score guidance

The pinned model transcribes the original mixture locally, with the official full-song overlapping-window inference and timestamp, rhythm, structure, key, full-chord and vocal-melody tasks. Instrumental-note transcription is omitted because the planner does not use it. Chords, vocal notes and structural labels are mapped by their timestamps onto the existing eight analysis slots per observed bar. The original acoustic profiles are copied before enrichment and remain unchanged on disk.

Chord and melody vectors require at least 50% slot coverage and cosine agreement above 0.55 with the separated accompaniment or vocal chroma. The contribution ramps with agreement and is capped at 25% for chords and 15% for melody. Melody also requires measured vocal activity. Unknown chords and uncovered or contradictory regions retain their acoustic features. This agreement is a heuristic cross-check, not calibrated model confidence. The normal sequence comparison and pitch-shift penalties then operate on the enriched features.

A predicted change of section contributes a soft cost only when both neighboring sections last at least two bars and the boundary lies within 30% of one bar of an observed downbeat. It neither moves the grid nor forcibly clips a phrase. Repeated identical labels are merged. Predicted intervals are not extrapolated more than two seconds beyond the final decoded event, preventing truncated output from describing the rest of a song. Structure estimates can still be wrong and do not establish lyrical context.

The worker is isolated from the server runtime and has no network access through the model loader (`local_files_only` plus Hub offline mode). It reads the original local WAV and writes analysis into a temporary directory. Only validated, completed results are cached, keyed by model revisions, schema version, track ID, file size and modification time. Cancellation terminates the worker without publishing partial results. Errors fall back to acoustic planning and are reported in the resulting plan. Raw events, ABC and MIDI remain local for inspection. Model weights and user media are never committed.

The optional models carry CC BY-NC 4.0 terms. This feature does not synthesize new audio with YuE2 and does not repair separation artifacts; it helps choose musical material for the existing renderer.

When at least eight vocal notes spanning eight seconds have been transcribed and the model reports no truncation warnings, the planner also measures vocal-note coverage per candidate. Coverage below 20% incurs a soft cost, capped at 0.28 per singer. This helps avoid treating separated synth or saxophone leakage as a vocal answer in an instrumental passage. Empty or failed transcriptions and uncovered audio regions incur no such cost. Missing model notes can still be false negatives, so this never excludes a candidate outright.

## V8: compare accompaniment handovers and local deformation

The planner now compares accompaniment changes at 8-bar positions within a 16-, 24- or 32-bar response (4 bars for an 8-bar response). B's vocal always stays continuous. Each candidate considers reverse vocal/harmony compatibility, outgoing-to-incoming chroma context, vocal activity at the handover, and internal backing-timbre changes. These are soft preferences, not cadence or voice-leading recognition.

Version 4 acoustic profiles add harmonic-accompaniment energy and MFCC novelty, independently from vocal novelty. Intro selection uses that energy rather than only drums. Local bar-to-target tempo ratios receive a reciprocal-symmetric soft cost beyond an 8% factor; that threshold is an engineering preference, not a guaranteed artifact boundary. Vocal candidates also distinguish delayed entries and long internal silences from ordinary breaths and trailing releases. Existing source stems and score caches remain reusable.

Auto tempo remains automatic across planning and resets when changing the song pair. Explicit tempo choices within a pair are preserved. The displayed tempo is sent to rendering. See [the composition research and implementation limits](mashup-composition-research.md), including classical form, thematic transformation, perception and modern mashup research.

The V8 grid check also validates bars against a local nine-bar median and the detector's four-beat count, rather than rejecting every passage outside one global song tempo. Sustained locally regular passages survive a tempo change; missed/doubled bars and non-four-beat detections remain excluded. This does not establish the true meter or repair faulty detections. A compact coherent plan can be preferable to a long forced arrangement.

## Optional C/D themes and full LALAL instrument separation

The optional guest planner adds one continuous 8/16-bar vocal theme per extra
track over the already-established B backing, with a four-bar instrumental
lead-in. It keeps the primary intro and A reprise, uses separate pitch choices,
and penalizes weak phrase boundaries, vocal gaps and local tempo deformation.
It is not a global four-song arrangement optimizer and does not understand lyrics.
A poor guest can still reduce coherence; an unsupported vocal passage produces
an actionable error rather than random jumps or invented repeated syllables.

`lalal_full` uses a separate cache and is never implicitly substituted for other
providers. Planning and rendering both use its vocals/drums/bass/reconstructed
other bus. Piano, guitars, synth, strings and wind are also available as individual
backing selections and source WAV downloads. These independent estimates may
contain bleed. The whole instrumental is used directly whenever selected; it is
not rebuilt by adding overlapping instrument estimates. Cloud quality still
needs a listening comparison on the user's material. Automated tests use a fake
provider and do not consume paid minutes.
