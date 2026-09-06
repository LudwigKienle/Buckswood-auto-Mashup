# Contributing

Buckswood auto Mashup is an early local production tool. Focused issues and pull requests are welcome.

For a bug, include your macOS version, Apple chip, the operation that failed, relevant error text and reproducible steps. Remove personal paths, track titles and other private information from logs before sharing. Use synthetic or openly licensed audio for fixtures and state its source and license.

For an audio-quality issue, include the output timestamp, source positions, target BPM, pitch shift and separation mode. Compare the same passage at a matched loudness. Explain what sounds wrong: a cut syllable, vocal leakage, an abrupt instrumental change or incompatible harmony. Technical checks cannot replace a listening comparison.

Run the tests and frontend build described in the README. Tests isolate their data from your music library. Do not commit audio, weights, environment files or local job metadata.

Useful directions include phrase and lyric-boundary detection, local harmonic compatibility, vocal cleanup that preserves consonants, rhythm-aware vocal placement for large tempo gaps, and support for other platforms. Please distinguish measured improvements from listening impressions.

Submit project-code contributions under GPL-3.0-only and preserve upstream attribution where applicable.
