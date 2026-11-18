# Verification of the 13 Delayed-Recognition ("Sleeping Beauty") Papers

**DPCN Group 15** · MANIT Bhopal, NIT Jamshedpur and NIT Silchar · Response to the Phase-1 review

## 1. Background

In Phase 1 we reported 13 papers (published 2016–2019) that received at most 3 citations in their first three years and 40 or more afterwards. For example, a 2019 MANIT paper on image-based anemia detection received 3 citations in 2019–2021 and 64 from 2022 onwards. The review asked us to check these papers carefully.

A slow start followed by a rise does not by itself show delayed recognition. It can also come from:

- **normal citation lag**: 50.4% of all papers in our data receive 3 or fewer citations in their first three years;
- **self-citation**: authors citing their own earlier paper in later work;
- **publication dates**: a paper published online late in the year has less than three real years in its "first three years";
- **an arbitrary threshold**: the rule "≤ 3, then ≥ 40" has no basis in the literature.

## 2. Method

We first confirmed that the list is reproducible: applying the Phase-1 rule to the yearly citation counts (OpenAlex) gives the same 13 papers, with identical counts, in both the Phase-1 data and the current data. Each paper was then tested in three ways [1]:

1. **Beauty coefficient B** (Ke et al., 2015 [2]), the standard measure of delayed recognition. B compares a paper's yearly citations with a straight line from its first year to its peak year. It is 0 for steady growth and rises with a longer quiet start and a sharper later rise. B was computed for all 8,228 cited faculty papers of 2016–2022, so each paper can be ranked against the whole corpus (Pctl. = percentile; Early = citations in the first three years).
2. **Self-citations removed**: citations from later papers by the same faculty were subtracted and B and the rule were recomputed.
3. **Publication dates**: online and print dates were taken from Crossref [3]. Where a paper appeared in November or December, or its issue date is later than its recorded year, the rule was re-applied from the following year.

Fixed criteria decide each verdict:

- **Holds up**: B in the top 1% of the corpus without self-citations, the rule still met, and no date problem.
- **Not supported**: B below the 90th percentile.
- **Weaker**: everything in between.

## 3. Results

| Paper (short title) | Inst. | Year | Early / later | Self-cites | B (no self) | Pctl. | Result |
|---|---|---|---|---|---|---|---|
| Feature selection with neuro-fuzzy approaches (review) | NITS | 2016 | 0 / 41 | 0 | 14.1 | 99.8 | **Holds up** |
| Noise in circular-gate TFET | NITS | 2016 | 3 / 62 | 18 | 10.6 | 99.6 | **Holds up** |
| CuFe₂O₄ nanoparticles as a gas sensor | MANIT | 2017 | 2 / 43 | 2 | 9.6 | 99.4 | **Holds up** |
| Multi-strut injection in a scramjet combustor | NITS | 2016 | 1 / 58 | 11 | 9.5 | 99.4 | **Holds up** |
| Anemia detection from eye-conjunctiva images | MANIT | 2019 | 3 / 64 | 0 | 9.2 | 99.3 | **Holds up** |
| Ground temperature variation | NITJ | 2017 | 0 / 62 | 0 | 8.9 | 99.2 | **Holds up** |
| Strength of geopolymer-stabilised clay | NITS | 2016 | 3 / 70 | 4 | 6.9 | 98.4 | Weaker |
| Multi-strut hydrogen injection (scramjet) | NITS | 2017 | 0 / 51 | 13 | 6.8 | 98.4 | Weaker |
| Hydrogen-fuelled scramjet, parallel strut | NITS | 2016 | 2 / 57 | 19 | 6.6 | 98.3 | Weaker |
| Polymer-matrix bio-composites (review) | NITS | 2018 | 3 / 40 | 1 | 4.6 | 95.5 | Weaker |
| Flower-pollination algorithm for generation control | NITJ | 2016 | 1 / 43 | 1 | 4.0 | 93.2 | Weaker |
| Grape-leaf disease detection | MANIT | 2017 | 3 / 61 | 0 | 4.0 | 93.2 | Weaker |
| Malaria-infected cell classification | NITS | 2016 | 3 / 43 | 3 | 2.2 | 85.2 | Not supported |

**Summary: 6 hold up, 6 are weaker and 1 is not supported.**

- **The six that hold up** rank in the top 1% of the corpus for delayed recognition, and removing self-citations does not change this. The anemia paper is among them, so the Phase-1 example stands.
- **Self-citation matters for some papers.** The three scramjet papers by the same two authors received 11–19 self-citations each. Two of them fall below the rule once these are removed.
- **Publication dates weaken two more.** The geopolymer and flower-pollination papers carry a Crossref issue date one or two years after their recorded year; counted from the next year, each has 6 early citations.
- **One case was an artefact.** The malaria paper went online on 30 December 2016, so its "first three years" were in effect two. Counted from 2017, it had 9 early citations, and its citations rise steadily rather than after a delay.

## 4. Interpretation and Limitations

- **These are short delays, not classic sleeping beauties.** The papers are at most ten years old. In the corpus the median B is 0.3 and the maximum 52.5, whereas the 1,000 strongest sleeping beauties in Web of Science have B ≥ 317.9 after decades of dormancy [2]. "Delayed recognition" describes our six cases more accurately.
- **Self-citations are counted only from papers by the same verified faculty.** Self-citations by co-authors outside the three institutes are not visible in our data.
- **2026 is a partial year.** Its citations count towards "later" but are not used for B.

## 5. Conclusion

The Phase-1 finding is partly confirmed. Six of the 13 papers show a robust delayed-recognition pattern, six show a weaker one, and one was an artefact of its publication date. We have corrected the claim accordingly. The full table, with each paper's yearly citations, is on the dashboard (Papers tab: "Which papers were recognised late, and does it hold up?"), and the analysis can be reproduced with `sleeping_beauties.py`.

## References

1. `sleeping_beauties.py` → `data/out/stats/sleeping_beauties.csv` (github.com/Avh09/DPCN_assgn2); yearly citation counts from OpenAlex
2. Ke, Q., Ferrara, E., Radicchi, F. & Flammini, A. (2015). Defining and identifying Sleeping Beauties in science. *PNAS*, 112(24), 7426–7431
3. Crossref REST API, publication dates retrieved 19 November 2026 (`data/ref/sleeping_beauty_dates.csv`)
