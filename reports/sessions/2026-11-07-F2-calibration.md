# F2 calibration (output of `uv run python -m app.sim.calibrate`)

Medians across seeds 0-49. Dates: out Sat 22 May, back Sun 6 Jun 2027 unless stated.

## Anchors

| Service | Source | Anchor £ | Simulated £ | Ratio |
| --- | --- | --- | --- | --- |
| EDI-MAD/easyJet | spec | 168 | 168 | 0.998 |
| EDI-MAD/Ryanair | fixture | 272 | 272 | 1.001 |
| EDI-STN/Ryanair | spec | 52 | 52 | 1.004 |
| EDI-LTN/easyJet | fixture | 76 | 77 | 1.017 |
| EDI-LHR/BA | fixture | 140 | 136 | 0.970 |
| EDI-CDG/easyJet | fixture | 153 | 152 | 0.997 |
| EDI-AMS/KLM | fixture | 190 | 193 | 1.014 |
| EDI-LIS/easyJet | fixture | 215 | 215 | 1.001 |
| EDI-BCN/Ryanair | fixture | 188 | 188 | 0.998 |
| MAD-LIM/AirEuropa | spec | 743 | 745 | 1.002 |
| MAD-LIM/Iberia | fixture | 769 | 770 | 1.001 |
| LHR-LIM/Avianca | spec | 710 | 716 | 1.008 |
| LHR-LIM/Iberia | fixture | 858 | 866 | 1.010 |
| CDG-LIM/AirFrance-Avianca | fixture | 774 | 771 | 0.997 |
| CDG-LIM/AirFrance | fixture | 1086 | 1086 | 1.000 |
| AMS-LIM/KLM | design | 850 | 863 | 1.015 |
| LIS-LIM/AirEuropa | fixture | 728 | 729 | 1.001 |
| BCN-LIM/LEVEL | fixture | 766 | 779 | 1.017 |
| EDI-LIM/KLM | spec | 1174 | 1190 | 1.014 |
| EDI-LIM/AirFrance | fixture | 1097 | 1111 | 1.013 |
| EDI-LIM/AirFrance-Avianca | fixture | 942 | 946 | 1.004 |
| EDI-LIM/Iberia | design | 985 | 995 | 1.010 |
| EDI-LIM/AirCanada | spec | 915 | 925 | 1.011 |
| LPB-MAD/BoA-AirEuropa | design | 652 | 654 | 1.003 |
| LPB-MAD/Avianca | design | 752 | 761 | 1.011 |
| LPB-LHR/Avianca | design | 731 | 731 | 1.000 |
| LPB-CDG/Avianca-AirFrance | design | 734 | 734 | 1.001 |
| LPB-BCN/Avianca | design | 741 | 756 | 1.020 |
| LPB-AMS/Avianca-KLM | design | 806 | 800 | 0.992 |
| LPB-EDI/Avianca-KLM | design | 822 | 811 | 0.987 |
| LPB-LIM/BoA | fixture | 226 | 229 | 1.015 |
| LPB-LIM/Avianca | fixture | 234 | 235 | 1.004 |

## Spec prices

| Spec | Real £ | Simulated £ |
| --- | --- | --- |
| London split: EDI-STN + LHR-LIM | 762 | 763 |
| Madrid split: EDI-MAD + MAD-LIM | 911 | 911 |
| Cheapest through EDI-LIM (Air Canada) | 915 | 920 |

## Date sensitivity, LHR-LIM return

Largest change from moving both dates by up to 3 days: median £15; £15 or more in 26/50 seeds (spec: under £15, from one observation).

## Cache bias, realistic (default)

| Route | Median cache / true lowest | Spread (p10-p90) |
| --- | --- | --- |
| MAD-LIM | 0.933 | 0.89-0.97 |
| LHR-LIM | 0.934 | 0.89-0.97 |
| CDG-LIM | 0.932 | 0.89-0.98 |
| AMS-LIM | 0.937 | 0.90-0.98 |
| LIS-LIM | 0.936 | 0.89-0.98 |
| BCN-LIM | 0.754 | 0.61-0.96 |
| EDI-MAD | 0.868 | 0.78-0.96 |
| EDI-STN | 0.886 | 0.79-0.97 |

## Cache bias, near-unbiased (UNBIASED_CACHE)

| Route | Median cache / true lowest | Spread (p10-p90) |
| --- | --- | --- |
| MAD-LIM | 0.997 | 0.98-1.01 |
| LHR-LIM | 1.000 | 0.98-1.02 |
| CDG-LIM | 0.999 | 0.98-1.02 |
| AMS-LIM | 1.000 | 0.98-1.02 |
| LIS-LIM | 1.001 | 0.98-1.02 |
| BCN-LIM | 1.007 | 0.90-1.10 |
| EDI-MAD | 0.996 | 0.95-1.05 |
| EDI-STN | 1.001 | 0.95-1.05 |

## La Paz premium (open-jaw minus Lima return, same hub long-haul)

| Hub | Back Sun 6 Jun £ | Back Sat 5 Jun £ |
| --- | --- | --- |
| MAD | 243 | 159 |
| LHR | 231 | 233 |
| CDG | 211 | 206 |
| AMS | 206 | 211 |
| LIS | no La Paz link | no La Paz link |
| BCN | 217 | 219 |
