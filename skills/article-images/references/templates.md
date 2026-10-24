# Templates

All images are 1200 by 900 (4:3), 56px rounded corners, near-black ink on one of five soft
colours (rose, butter, mint, sky, lilac). The slug chooses the colour and the details. The
figure image is always a different colour from the cover.

| Template | What it looks like | Good for | Do not use for |
|---|---|---|---|
| `compare-blocks` | One large dark block and one smaller white block, area proportional to the two values | Two things with the same kind of number | More than two things, unlike units |
| `figure-ripples` | Giant number with concentric rings | One standout amount | Several numbers |
| `waveform` | Row of rounded bars like an audio wave, big number below | Speech, audio, signals, performance rates | Counts of things |
| `constellation` | Big number beside a hub linked to 3 to 9 nodes | Counts of connected things | Anything over 9 or under 3 |
| `spectrogram` | Grid of rounded cells, short word or number below | Benchmarks, datasets, evaluations | Process descriptions |
| `layers` | Three stacked pills with text | Three steps or components | Numbers, comparisons |

## Writing good fields

- **label:** the topic, two to four words. `SPEECH RECOGNITION`, `FUNDING`, `HOW IT WORKS`.
- **figure:** the number as printed in the article: `5.06%`, `$118M`, `1,500`, `24.3`. Keep the unit symbol if it fits in 8 characters, else move the unit to the caption.
- **caption:** what the figure measures, lower case, no full stop: `word error rate`, `hours of public audio`.
- **alt:** `A speech waveform above the 5.06% word error rate of Granite Speech 5.0 2B.`
- **layers items:** short noun phrases, 30 characters at most, in reading order.

## Examples

See `examples/`. `granite-*` is the first article. `example-news-*` and `example-paper-*` show
the same rules applied to other articles; they change the template, the colour and the details.
