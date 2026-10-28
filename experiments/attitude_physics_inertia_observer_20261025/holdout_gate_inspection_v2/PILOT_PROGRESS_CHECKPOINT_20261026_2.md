# GHP7 pilot progress checkpoint 2026-10-26 (2)

- Active release revision 7, SHA-256 7149c50c8f323fe0ee4736f8a433003be9b0e5c7b94542a6a48eaadcad5f5856.
- Completed 36/54 calls across G1/W00, G1/W12, G2/W00, and G2/W12. All completed runs report 20,000 transitions, 20,001 samples, STABLE; all raw hashes matched their status records; no safety stop.
- One partial score exists for the first two scenes: pilot_score_after_G1_W12_v1 (18/54). Do not treat it as the final full-pilot result. Scene-level audit files preserve observed metrics and the two fixed-bound15 clearance failures.
- Remaining scenes: G3/W00 and G3/W12 (18 calls each). No TEST or model training has started.
- Next: B G3/W00, six ACTIVE candidate arms, then fixed C5_11 MIN and BOUND15; repeat for G3/W12. Run one final full scorer after all 54 slots are present. Then decide which reconstruction/observer terms are dispensable and prepare the DL attitude-head taskbook.
- Disk C free: 142.3 GB. No historical MAT/model/cache was deleted.
