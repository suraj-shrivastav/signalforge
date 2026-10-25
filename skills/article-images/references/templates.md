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
| `bar-chart` | 3 to 6 horizontal bars on one scale from zero, the first (the subject) dark, values after the bars | One metric across several named things | Different units, or a single number |
| `architecture` | 3 to 5 rounded boxes joined by arrows, reading left to right and wrapping to a second row | How data moves through a system | Comparisons, a single number, more than 5 parts |

## Writing good fields

- **label:** the topic, two to four words. `SPEECH RECOGNITION`, `FUNDING`, `HOW IT WORKS`.
- **figure:** the number as printed in the article: `5.06%`, `$118M`, `1,500`, `24.3`. Keep the unit symbol if it fits in 8 characters, else move the unit to the caption.
- **caption:** what the figure measures, lower case, no full stop: `word error rate`, `hours of public audio`.
- **alt:** `A speech waveform above the 5.06% word error rate of Granite Speech 5.0 2B.`
- **layers items:** short noun phrases, 30 characters at most, in reading order.

## Examples

See `examples/`. `granite-*` is the first article. `example-bar-chart-*` shows the bar chart with a ripples cover. `example-architecture-*` shows the architecture template with a ripples cover. `example-news-*` and `example-paper-*` show
the same rules applied to other articles; they change the template, the colour and the details.
