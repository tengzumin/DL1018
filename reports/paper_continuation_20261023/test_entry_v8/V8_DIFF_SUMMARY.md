# v8 code-only path binding repair

v8 resolves the MATLAB manifest from the relative path recorded in the contract, then derives reportDir from that resolved path. This fixes the v7 prepare failure: the entry still pointed reportDir at test_entry_v6 and MATLAB rejected the manifest hash. The v7 receipt and logs remain preserved and are recorded in the v8 manifest; v6 failure evidence remains intact.

The cumulative disk guards count v3-v7 historical output/report directories plus the current v8 directories. Method objects, source/model references, corrected engineering references, frozen TEST input identities, and protected scientific/runtime functions are retained from v7.

Validation is static only: PowerShell AST and JSON checks, contract-bound manifest path resolution, budget path checks, and protected-function identity checks. No MATLAB, Plant, TEST, training, or reader was run.

Static SHA256:
entry 7ec9f28758005fded65d6507138a68a296ad4bfa1fc88443936302743bf9bdab
launcher 7045a7f70a4ff63fb52976ee0652de9358d200bab19501e40af84c4b9c483d12
contract a1dee01f87502cf683c4513c0d8e56ac82c493579a927a6803a6587bf0638728
manifest 7b7c0600838aa51e0033d0d4dd1808f9d711ceb4f1bcc1c4f8ebf280cc2fa43f