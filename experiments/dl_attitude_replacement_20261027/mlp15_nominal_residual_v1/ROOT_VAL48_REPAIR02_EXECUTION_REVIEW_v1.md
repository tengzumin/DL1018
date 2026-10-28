# Root review: REPAIR02 one-shot C5_VAL48 diagnostic

Date: 2026-10-27 (Asia/Shanghai)

## Review result

Approve exactly one numeric C5_VAL48 offline diagnostic using the REPAIR02 executor after changing its execution lock to `ROOT_RELEASED_FOR_ONE_SHOT_SCORE` and `score_execution_authorized=true`.

The original REPAIR01 attempt is preserved and did not read numerical VAL arrays. Its scorer stopped at the isolated MATLAB parity path guard before creating a score-start marker; it completed 0 scenes and 0 events. REPAIR02 places byte-identical parity artifacts under its output directory and derives a score lock that changes only the parity manifest, report, and artifact paths.

## Root checks

- REPAIR02 metadata audit and scorer preflight: PASS, 48 scenes, 144 identity files; V2/V3/V1 counts 11/36/1; 16 locked `_ACC_FIX_V1` aliases. Numeric VAL arrays, score-start marker, TEST, Plant, training, and closed-loop are all false.
- Copied parity manifest SHA-256 remains `df526ee5a5fa510f8d7d37848ebb0baac7e8328d45c0c50ad1593a22d20ef76c`; all eight listed artifact hashes match, including the weights and parity fixture.
- Derived score lock SHA-256: `e9dd76aca1cfb3df070c32c25b9d1a5df15a155b2a34d7d3f46cebaee5e75391`. Independent comparison confirms only parity paths differ from the original lock.
- Executor syntax parses. Its SHA-256 is `b3eaee2ff1440744497115df69a3411fd95e870940858f5d9900e0a68ee52706`.
- Before root release, execution lock SHA-256 is `812d971c864832d4aaebe6b094c3bf9704b8ba5db381e7a3afc5650fa62fae5e`; all 56 bound-file SHA-256 values match. The lock currently authorizes no score.
- The executor refuses any existing score or execution output, repeats the metadata audit and scorer preflight in the same invocation, then calls the frozen scorer once. It writes only under `C5_VAL48_OFFLINE_DIAGNOSTIC_REPAIR02` and does not train, access TEST, call Plant, or run closed-loop code.

## Bound artifacts

- ADDENDUM05 SHA-256: `c021b25451677458c7e4e750b4bc502ebaa6b62470c6b86e320e541c784b35b5`
- ADDENDUM06 SHA-256: `c55c2d0d99ce55e5fa4d8636d0f19c5dc42e2b7675dc78f97eaf9ee93f6081bf`
- Metadata audit SHA-256: `b8d3e5e93f5e6f29cd9cb1a5016d6fad86f02a6f2b026d19a0c3a8f1b1c8e454`
- Identity mapping CSV SHA-256: `02cf9fa543c7bd2428a9046ac3b364c7a2012505e7e7a5f837671b2770938c83`
- Preflight receipt SHA-256: `546dd3c53566b129a14dde3eda3e8c0cf8fc67399a629bd4787eddce7348a690`
- Preparation hash manifest SHA-256: `5b69e1e7ee79d287a5bb57d917ca9e677a94805eea15f12cb3e554a7b8343bdd`
