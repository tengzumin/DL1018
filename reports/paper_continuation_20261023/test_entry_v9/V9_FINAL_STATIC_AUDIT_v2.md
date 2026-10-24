# v9 最终静态审计 v2

状态：PASS_CODEONLY_WAITING_FOR_PARENT_REVIEW。仅静态核验；未运行 MATLAB、Plant、训练或 TEST 性能读取。

唯一逻辑变化为阶段任务书路径绑定与 `read_method_contract` 精确双身份适配；另更新 v9/v2 元数据、SHA 及历史磁盘预算。完整四文件 diff 见本文末。旧 `V9_PATH_AUDIT_SUMMARY.md` 原样保留，SHA256 为 `62edcb06b798236bfc1306b5b1bc1fd582caeee0475a7d18875bf4cce44f1923`，其中先前标注的 metadata 阻断已由本 v2 修复。

静态结果：PowerShell AST 错误 0；两 JSON 解析通过；331 个 path/hash 绑定及 1 个 runtime tree 精确核验通过，共散列 120 个唯一文件（含 runtime tree 子文件）。六方法对象、source/model refs、engineering specs、三项冻结 TEST 输入及 execution/limits 与 v7、v8 完全一致。六个保护函数规范换行文本 exact：run_one_method、compare_raw_tree、compare_engineering_raw、bind_method_path、verify_global_platform_which、prepare_no_plant。MATLAB 相对 v8 只改变 verify_stage_release、read_method_contract、assert_budget。

实际路径链：MATLAB 由当前 here 读取 contract，按 repo_path(root,contract.method_source_manifest_path) 读取 v9 manifest，再以 fileparts 得到 reportDir；verify_code_contract 的任务书、code-only release、dependency review、v3 source manifest 均来自 contract。verify_stage_release 读取同一传入 contractPath，并按 contract.taskbook_path 读取 v2 任务书，原 schema、五 SHA、Plant/TEST/training/no_retry 门禁 exact。三个阶段的 release/result/OS receipt 均由 reportDir 派生，DEV2/TEST raw 与 marker 均由 here 派生。PowerShell reportDir、taskbook、codeRelease、manifest 和 MATLAB addpath 都指向 v9/v2，并与 contract 的实际文件一致。

保留的旧路径均有明确用途：V3 的共享输入与 freeze receipts、B48 复用和未启动组合 guard；v3-v8 输出/report 仅累计预算；各版本失败证据只作历史绑定。D/K 的历史 run_start/raw 分别锁到 corrected r002/r001，与 method snapshot 路径/SHA 一致。没有错误的旧版本活动文件路径。

metadata 消费者逐项核对：

| 读取或消费处 | 校验及输出 |
| --- | --- |
| verify_code_contract / release / PS 方法列表 | canonical method_id、顺序与 alias 保持六方法冻结身份 |
| run_engineering_dev2 的 prior.meta | 使用 engineering_spec.peer_legacy_method_id，精确要求 CORRECTED_TRAIN_*；source/runtime scene_id 仍为固定 VAL 场景 |
| read_method_contract 的 D/K fallback | DSSM historical 只接受 CORRECTED_TRAIN_DSSM14_G12_R32，部署 candidate/collector 仍 DSSM14_G12_R32；KAN historical 只接受 CORRECTED_TRAIN_KAN14_G12_R32，部署 candidate/collector 仍 NEW_KAN14_G12_R32；未知 corrected 显式 error；实际 snapshot 路径/SHA 及原 assert 保留 |
| DEV2 的 candidate/collector、TEST 的 method_candidate/collector_tag | 均消费上述部署标签，不再把历史训练记录身份当作 collector；canonical method_id 不变 |
| 冻结 wrapper / compare_engineering_raw | wrapper 仍以 B2-RBF-Full-SPLIT 调用 core，仅附加 scene_id/collector；comparison 原 schema、字符串及完整 numeric gate 不变 |
| build_method_snapshot / method_preflight_summary / runIdentity | 仍使用原 model_id、模型/W0/normalizer 数组及 canonical method_id，未改科学数值；B/C5 的 run_contract 读取分支未改 |

数值实核：h5py 只读所锁 DEV run_start/C5 prepared snapshots，scipy 只读外部模型，numpy 只读冻结 normalizer。五个带模型方法均通过全部 15 个模型字段精确比较、runtime.weight 与 head.W0 精确比较；三个 C5 snapshot 顶层 W0 同样精确。模型 input_mu/input_sigma 与 normalizer NPZ 精确相等。DSSM/C5 W0 SHA 为 `88f8c4f2495438c3797655c48bab1bf0c11ac2e27bff1f5f2a7423a8f0a2cf53`；KAN W0 SHA 为 `acd52fe281d2f7c1a801afe304b96896a4434ff8c084c9f9d0c387dfa8187b4a`；共同 normalizer 数组 SHA 为 `533aad9a2c66874cfa67f5d268661835e81e58b797cba7d6fc1c12d4013de5f0`。B 无外部学习模型；其 snapshot/source SHA 已纳入上述绑定核验。未读取 TEST 场景数组或任何 TEST 分数。

四个实际字节 SHA256：

```text
entry b9906578088319c8108a360c140c163b8af9080f311613489a20a48a8f609fd1
launcher 7034e2e6d5459fb33e9a66dcc2ad32c80677b7850a1eacd510b6d1648d631c8c
contract d4132d2a00693bde5ca234e4ac7cf07ba2695971a086b2275539842d7f5c3210
manifest f8998debf70835d0fb4dcab8c9d8fe77ef1702be80559622badd3dafa1b77d80
```

完整 diff（v8 → 最终 v9；只规范显示换行）：

```diff
--- experiments/c5_test48_v8/test48_entry_v4.m
+++ experiments/c5_test48_v9/test48_entry_v4.m
@@ -177,7 +177,8 @@
 function release=verify_stage_release(path,schema,status,contractPath,manifestPath,plant,sceneGeneration,testAccess)
 assert(isfile(path),'TEST48V4:ParentRelease','The separate parent stage release is missing: %s.',path);
 release=jsondecode(fileread(path)); root=fileparts(fileparts(fileparts(mfilename('fullpath'))));
-taskbookPath=fullfile(root,'reports','paper_continuation_20261023','TEST_UNSTARTED_DEPENDENCY_REPAIR_TASKBOOK_v4_ZH.md');
+contract=jsondecode(fileread(contractPath));
+taskbookPath=repo_path(root,char(contract.taskbook_path));
 launcherPath=fullfile(fileparts(mfilename('fullpath')),'RUN_TEST48_EXACT_v1.ps1');
 assert(isfield(release,'schema')&&strcmp(release.schema,schema)&&isfield(release,'status')&&strcmp(release.status,status), ...
     'TEST48V4:ParentRelease','Parent release schema/status mismatch.');
@@ -778,12 +779,14 @@
         'TEST48:HistoricalRunStartMetadata','Historical corrected run_start lacks its actual meta.method_id.');
     actual=char(old.meta.method_id);
     if strcmp(char(m.method_id),'CORRECTED_DSSM14_G12_R32')
-        expected='DSSM14_G12_R32';
+        expected='CORRECTED_TRAIN_DSSM14_G12_R32'; deployed='DSSM14_G12_R32';
+    elseif strcmp(char(m.method_id),'CORRECTED_KAN14_G12_R32')
+        expected='CORRECTED_TRAIN_KAN14_G12_R32'; deployed='NEW_KAN14_G12_R32';
     else
-        expected='NEW_KAN14_G12_R32';
+        error('TEST48:HistoricalMethodId','Unknown corrected method identity: %s.',char(m.method_id));
     end
     assert(strcmp(actual,expected),'TEST48:HistoricalMethodId','Historical run_start method id differs from the locked identity.');
-    methodContract=struct('candidate',actual,'collector_tag',actual);
+    methodContract=struct('candidate',deployed,'collector_tag',deployed);
     return
 end
 assert(isfile(char(m.run_contract_path))&&strcmpi(sha256_file(char(m.run_contract_path)),char(m.run_contract_sha256)), ...
@@ -902,11 +905,12 @@
 v5out=fullfile(root,'experiments','c5_test48_v5'); v5report=fullfile(root,'reports','paper_continuation_20261023','test_entry_v5');
 v6out=fullfile(root,'experiments','c5_test48_v6'); v6report=fullfile(root,'reports','paper_continuation_20261023','test_entry_v6');
 v7out=fullfile(root,'experiments','c5_test48_v7'); v7report=fullfile(root,'reports','paper_continuation_20261023','test_entry_v7');
+v8out=fullfile(root,'experiments','c5_test48_v8'); v8report=fullfile(root,'reports','paper_continuation_20261023','test_entry_v8');
 assert(double(limits.prior_created_bytes)+directory_bytes(v3out)+directory_bytes(v3report)+ ...
     directory_bytes(v4out)+directory_bytes(v4report)+directory_bytes(v5out)+directory_bytes(v5report)+ ...
     directory_bytes(v6out)+directory_bytes(v6report)+directory_bytes(v7out)+directory_bytes(v7report)+ ...
-    directory_bytes(outputRoot)+directory_bytes(reportRoot)+reserve<=double(limits.max_output_bytes), ...
-    'TEST48V4:OutputCap','Cycle-wide baseline plus v3/v4/v5/v6/v7/v8 output and remaining reserve exceeds the cap.');
+    directory_bytes(v8out)+directory_bytes(v8report)+directory_bytes(outputRoot)+directory_bytes(reportRoot)+reserve<=double(limits.max_output_bytes), ...
+    'TEST48V4:OutputCap','Cycle-wide baseline plus v3/v4/v5/v6/v7/v8/v9 output and remaining reserve exceeds the cap.');
 required=double(remainingSceneCalls)*double(limits.per_scene_seconds_guard)+ ...
     double(remainingProcesses)*double(limits.process_exit_buffer_seconds);
 assert(seconds(deadline-datetime('now','TimeZone','UTC'))>=required, ...
--- experiments/c5_test48_v8/RUN_TEST48_EXACT_v1.ps1
+++ experiments/c5_test48_v9/RUN_TEST48_EXACT_v1.ps1
@@ -6,11 +6,11 @@
 $ErrorActionPreference = 'Stop'
 $taskDir = [IO.Path]::GetDirectoryName($PSCommandPath)
 $repoRoot = [IO.Path]::GetFullPath((Join-Path $taskDir '..\..'))
-$reportDir = Join-Path $repoRoot 'reports/paper_continuation_20261023/test_entry_v8'
+$reportDir = Join-Path $repoRoot 'reports/paper_continuation_20261023/test_entry_v9'
 $contractPath = Join-Path $taskDir 'TEST48_RUN_CONTRACT_v4.json'
 $manifestPath = Join-Path $reportDir 'TEST_METHOD_SOURCE_MANIFEST_v4.json'
-$taskbookPath = Join-Path $repoRoot 'reports/paper_continuation_20261023/TEST_ENTRY_PATH_BINDING_REPAIR_TASKBOOK_v1_ZH.md'
-$codeReleasePath = Join-Path $repoRoot 'reports/paper_continuation_20261023/TEST_ENTRY_PATH_BINDING_REPAIR_CODE_ONLY_RELEASE_v1.json'
+$taskbookPath = Join-Path $repoRoot 'reports/paper_continuation_20261023/TEST_STAGE_PATH_CONTRACT_REPAIR_TASKBOOK_v2_ZH.md'
+$codeReleasePath = Join-Path $repoRoot 'reports/paper_continuation_20261023/TEST_STAGE_PATH_CONTRACT_REPAIR_CODE_ONLY_RELEASE_v2.json'
 $dependencyReviewPath = Join-Path $repoRoot 'reports/paper_continuation_20261023/test_dependency_review_v1/DEPENDENCY_REVIEW_v1.json'
 $matlabExe = 'C:/Program Files/MATLAB/R2025b/bin/matlab.exe'
 $methodIds = @('B_TRACEABLE','CORRECTED_DSSM14_G12_R32','CORRECTED_KAN14_G12_R32','C5_M110','C5_FREEZE_TRAINED_W0','C5_NO_DELAYED_PREDICTION')
@@ -184,8 +184,10 @@
     $v6report = Join-Path $repoRoot 'reports/paper_continuation_20261023/test_entry_v6'
     $v7out = Join-Path $repoRoot 'experiments/c5_test48_v7'
     $v7report = Join-Path $repoRoot 'reports/paper_continuation_20261023/test_entry_v7'
-    $used = [int64]$limits.prior_created_bytes + (Get-DirectoryBytes $v3out) + (Get-DirectoryBytes $v3report) + (Get-DirectoryBytes $v4out) + (Get-DirectoryBytes $v4report) + (Get-DirectoryBytes $v5out) + (Get-DirectoryBytes $v5report) + (Get-DirectoryBytes $v6out) + (Get-DirectoryBytes $v6report) + (Get-DirectoryBytes $v7out) + (Get-DirectoryBytes $v7report) + (Get-DirectoryBytes $taskDir) + (Get-DirectoryBytes $reportDir) + $reserve
-    if ($used -gt [int64]$limits.max_output_bytes) { throw 'Cycle-wide v3/v4/v5/v6/v7/v8 outputs plus remaining reserve exceed the 80e9-byte cap.' }
+    $v8out = Join-Path $repoRoot 'experiments/c5_test48_v8'
+    $v8report = Join-Path $repoRoot 'reports/paper_continuation_20261023/test_entry_v8'
+    $used = [int64]$limits.prior_created_bytes + (Get-DirectoryBytes $v3out) + (Get-DirectoryBytes $v3report) + (Get-DirectoryBytes $v4out) + (Get-DirectoryBytes $v4report) + (Get-DirectoryBytes $v5out) + (Get-DirectoryBytes $v5report) + (Get-DirectoryBytes $v6out) + (Get-DirectoryBytes $v6report) + (Get-DirectoryBytes $v7out) + (Get-DirectoryBytes $v7report) + (Get-DirectoryBytes $v8out) + (Get-DirectoryBytes $v8report) + (Get-DirectoryBytes $taskDir) + (Get-DirectoryBytes $reportDir) + $reserve
+    if ($used -gt [int64]$limits.max_output_bytes) { throw 'Cycle-wide v3/v4/v5/v6/v7/v8/v9 outputs plus remaining reserve exceed the 80e9-byte cap.' }
     $deadline = Convert-DeadlineUtc $limits.hard_deadline_utc
     $required = ([int64]$SceneCalls * [int64]$limits.per_scene_seconds_guard) + ([int64]$Processes * [int64]$limits.process_exit_buffer_seconds)
     if (($deadline - [DateTime]::UtcNow).TotalSeconds -lt $required) { throw 'Conservative remaining deadline guard failed.' }
@@ -223,7 +225,7 @@
     $env:MATLAB_PREFDIR = $pref
     $rootForMatlab = $repoRoot.Replace('\','/').Replace("'","''")
     $stageArg = $Stage.Replace("'","''"); $methodArg = $Method.Replace("'","''")
-    $expr = "try; cd('$rootForMatlab'); addpath('experiments/c5_test48_v8'); test48_entry_v4('$stageArg','$methodArg'); quit(0,'force'); catch ME; fprintf(2,'%s\n',getReport(ME,'extended','hyperlinks','off')); quit(1,'force'); end"
+    $expr = "try; cd('$rootForMatlab'); addpath('experiments/c5_test48_v9'); test48_entry_v4('$stageArg','$methodArg'); quit(0,'force'); catch ME; fprintf(2,'%s\n',getReport(ME,'extended','hyperlinks','off')); quit(1,'force'); end"
     $argLine = '-singleCompThread -wait -batch "' + $expr + '"'
     $started = [DateTime]::UtcNow.ToString('o')
     $proc = $null
--- experiments/c5_test48_v8/TEST48_RUN_CONTRACT_v4.json
+++ experiments/c5_test48_v9/TEST48_RUN_CONTRACT_v4.json
@@ -1,15 +1,15 @@
 {
   "schema": "TEST48_RUN_CONTRACT_V4",
   "state": "CODE_ONLY_WAITING_FOR_SEPARATE_STAGE_RELEASES",
-  "version": "c5_test48_v8",
-  "taskbook_path": "reports/paper_continuation_20261023/TEST_ENTRY_PATH_BINDING_REPAIR_TASKBOOK_v1_ZH.md",
-  "taskbook_sha256": "49a8a408dad299692bbde207a70bf57ac3d03db16f8613c9b6293007c3cb337c",
-  "code_only_release_path": "reports/paper_continuation_20261023/TEST_ENTRY_PATH_BINDING_REPAIR_CODE_ONLY_RELEASE_v1.json",
-  "code_only_release_sha256": "63ede7d7ac080dd146f08fac2f2af32d479d1a588709e5fe6a548ce23ebc7dc2",
+  "version": "c5_test48_v9",
+  "taskbook_path": "reports/paper_continuation_20261023/TEST_STAGE_PATH_CONTRACT_REPAIR_TASKBOOK_v2_ZH.md",
+  "taskbook_sha256": "3d93cd4419cc86d8e1fa7e9e64b34399320f4a8a46726a2423e403e4093c0d9f",
+  "code_only_release_path": "reports/paper_continuation_20261023/TEST_STAGE_PATH_CONTRACT_REPAIR_CODE_ONLY_RELEASE_v2.json",
+  "code_only_release_sha256": "9f4876e732d00415b8be5a14383e36f74dab961f1aabd7a9571377ace9bd7732",
   "dependency_review_path": "reports/paper_continuation_20261023/test_dependency_review_v1/DEPENDENCY_REVIEW_v1.json",
   "dependency_review_sha256": "dc9d9ab261bc13ee08fd733b961acf56396e1da8eb945fc15455a1b2b2d3d4b7",
-  "method_source_manifest_path": "reports/paper_continuation_20261023/test_entry_v8/TEST_METHOD_SOURCE_MANIFEST_v4.json",
-  "method_source_manifest_sha256": "7b7c0600838aa51e0033d0d4dd1808f9d711ceb4f1bcc1c4f8ebf280cc2fa43f",
+  "method_source_manifest_path": "reports/paper_continuation_20261023/test_entry_v9/TEST_METHOD_SOURCE_MANIFEST_v4.json",
+  "method_source_manifest_sha256": "f8998debf70835d0fb4dcab8c9d8fe77ef1702be80559622badd3dafa1b77d80",
   "v3_source_manifest_path": "reports/paper_continuation_20261023/test_entry_v3/TEST_METHOD_SOURCE_MANIFEST_v1.json",
   "v3_source_manifest_sha256": "b9ed7fef91bf61b03e4f51d8a9cbaf7233484ac6faa4750827aefb7e247f9633",
   "v3_frozen_inputs": {
@@ -117,10 +117,10 @@
     "hard_deadline_utc": "2026-10-24T17:01:00Z",
     "minimum_free_bytes_after_reserve": 30000000000
   },
-  "entry_path": "experiments/c5_test48_v8/test48_entry_v4.m",
-  "entry_sha256": "7ec9f28758005fded65d6507138a68a296ad4bfa1fc88443936302743bf9bdab",
-  "launcher_path": "experiments/c5_test48_v8/RUN_TEST48_EXACT_v1.ps1",
-  "launcher_sha256": "7045a7f70a4ff63fb52976ee0652de9358d200bab19501e40af84c4b9c483d12",
+  "entry_path": "experiments/c5_test48_v9/test48_entry_v4.m",
+  "entry_sha256": "b9906578088319c8108a360c140c163b8af9080f311613489a20a48a8f609fd1",
+  "launcher_path": "experiments/c5_test48_v9/RUN_TEST48_EXACT_v1.ps1",
+  "launcher_sha256": "7034e2e6d5459fb33e9a66dcc2ad32c80677b7850a1eacd510b6d1648d631c8c",
   "global_platform_lock_sha256": "f7c756e8f7473f3ddba18e35618fd5c0487c3f42d234cca9366727fc0719d738",
   "global_platform_ref_count": 32
 }
--- reports/paper_continuation_20261023/test_entry_v8/TEST_METHOD_SOURCE_MANIFEST_v4.json
+++ reports/paper_continuation_20261023/test_entry_v9/TEST_METHOD_SOURCE_MANIFEST_v4.json
@@ -1304,8 +1304,8 @@
   "source_path_note": "Corrected pair sources remain read-only at their original runtime paths. No TEST scene arrays or outcome raws were read.",
   "schema": "TEST48_METHOD_SOURCE_MANIFEST_V4",
   "status": "CODE_ONLY_CANDIDATE_WAITING_FOR_ROOT_REVIEW",
-  "taskbook_sha256": "49a8a408dad299692bbde207a70bf57ac3d03db16f8613c9b6293007c3cb337c",
-  "code_only_release_sha256": "63ede7d7ac080dd146f08fac2f2af32d479d1a588709e5fe6a548ce23ebc7dc2",
+  "taskbook_sha256": "3d93cd4419cc86d8e1fa7e9e64b34399320f4a8a46726a2423e403e4093c0d9f",
+  "code_only_release_sha256": "9f4876e732d00415b8be5a14383e36f74dab961f1aabd7a9571377ace9bd7732",
   "v3_source_manifest_path": "reports/paper_continuation_20261023/test_entry_v3/TEST_METHOD_SOURCE_MANIFEST_v1.json",
   "v3_source_manifest_sha256": "b9ed7fef91bf61b03e4f51d8a9cbaf7233484ac6faa4750827aefb7e247f9633",
   "dependency_review_path": "reports/paper_continuation_20261023/test_dependency_review_v1/DEPENDENCY_REVIEW_v1.json",
@@ -1635,7 +1635,7 @@
     "expected_v3_dssm_first_plant": false,
     "expected_v3_b_os_exit": 0
   },
-  "taskbook_path": "reports/paper_continuation_20261023/TEST_ENTRY_PATH_BINDING_REPAIR_TASKBOOK_v1_ZH.md",
+  "taskbook_path": "reports/paper_continuation_20261023/TEST_STAGE_PATH_CONTRACT_REPAIR_TASKBOOK_v2_ZH.md",
   "v6_incorrect_dk_reference_bindings": [
     {
       "method_id": "CORRECTED_DSSM14_G12_R32",
@@ -1660,6 +1660,7 @@
       "note": "Historical v3/v6 template binding preserved as superseded; corrected r001/r002 archive is the actual reference."
     }
   ],
+  "v8_prepare_failure_evidence": {"mode":"PREPARE_NO_PLANT","attempt":"v8","os_exit_path":"reports/paper_continuation_20261023/test_entry_v8/PREPARE_NO_PLANT_MATLAB_OS_EXIT_v1.json","os_exit_sha256":"004e93d8d3fb094acdb4cee3d4a4b147294fc3c7402b5cf7acf80c6a71ba5878","matlab_os_exit_code":1,"natural_wait_used":true,"started_utc":"2026-10-23T17:04:16.9451410Z","completed_utc":"2026-10-23T17:04:28.0181310Z","stderr_path":"reports/paper_continuation_20261023/test_entry_v8/logs/PREPARE_NO_PLANT.stderr.log","stderr_sha256":"0d2716ccf6f30fc83b35622af536165b4c5c482db564c1a4bfe359ed2367a2e7","stdout_path":"reports/paper_continuation_20261023/test_entry_v8/logs/PREPARE_NO_PLANT.stdout.log","stdout_sha256":"e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855","TEST_accessed":true,"plant_authorized":false,"plant_calls":0,"result_present":false,"failure_json_present":false,"error":"Parent release does not bind exact v4 taskbook, contract, manifest, entry, and launcher.","identified_cause":"verify_stage_release still used the original v4 taskbook while the contract and parent stage release bound the v8 taskbook; failure preceded prepare_no_plant."},
   "v7_prepare_failure_evidence": {"mode":"PREPARE_NO_PLANT","attempt":"v7","os_exit_path":"reports/paper_continuation_20261023/test_entry_v7/PREPARE_NO_PLANT_MATLAB_OS_EXIT_v1.json","os_exit_sha256":"355a6d7373dd3e64d8fa06d2fd911927a9014cca45be21229a294646b4cba3d8","matlab_os_exit_code":1,"natural_wait_used":true,"started_utc":"2026-10-23T16:48:35.6627064Z","completed_utc":"2026-10-23T16:49:05.9804252Z","session_id":55889,"matlab_pid":100924,"stderr_path":"reports/paper_continuation_20261023/test_entry_v7/logs/PREPARE_NO_PLANT.stderr.log","stderr_sha256":"8a3c16076b8fe150fe1afe219bd56a97076acd61cfbed4c4489c0ec212f03fbc","stdout_path":"reports/paper_continuation_20261023/test_entry_v7/logs/PREPARE_NO_PLANT.stdout.log","stdout_sha256":"e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855","TEST_accessed":true,"plant_authorized":false,"plant_calls":0,"result_present":false,"failure_json_present":false,"error":"The contract does not bind the candidate manifest.","identified_cause":"The v7 MATLAB entry hard-coded test_entry_v6 for reportDir and therefore loaded the v6 manifest before contract verification."},
   "v6_dev2_failure_evidence": {
     "failure_path": "reports/paper_continuation_20261023/test_entry_v6/ENGINEERING_DSSM_FAILURE_v1.json",

```
