# v9 stage taskbook path repair (CODEONLY)

The top loader reads its local contract, resolves contract.method_source_manifest_path with repo_path, and derives reportDir from that manifest. verify_stage_release now reads the same passed contractPath and resolves contract.taskbook_path with repo_path. Its schema, five SHA comparisons, Plant/TEST/training flags, and no_retry checks are unchanged. The PowerShell report/taskbook/code-release/addpath paths target v9 and agree with the contract. All stage evidence paths derive from reportDir; runtime outputs derive from here/taskDir. Historical v3 frozen input and B48/combination guards remain intentional. Disk guards include v3-v8 historical output/report directories plus current v9. v8 failure evidence is preserved in the manifest.

Separate known static blocker (not changed under this release): read_method_contract loads corrected r002/r001 meta.method_id but still expects the old collector labels; the actual corrected metadata strings are CORRECTED_TRAIN_DSSM14_G12_R32 and CORRECTED_TRAIN_KAN14_G12_R32. This is reached by DEV2 before Plant. No DEV2 readiness is claimed.

No MATLAB, Plant, training, or TEST performance reader was run.

Static SHA256:
entry 4d44a5367f79e2666ccaca0445358b246da53cee08dabbf9857db9108822dce5
launcher 4d9162ee05d30166a098c591348b87d72c7cc6db326687ecc64f063528df489b
contract ebbaea0374113e153940a014fb7bba7d5b3971c1abc78ccb597c031a6d98e1e8
manifest 9dc615ec628b5b59be38cf7bd50d786f3b5e44a4a09af14cf202e058b77a88d8
