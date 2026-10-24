# C6 入口源码冻结审查

状态：SOURCE_BOUND_NO_PLANT_PARENT_REVIEW_REQUIRED_V1。本交付完成C6隔离入口的代码静态修复和源码锁刷新；它不构成MATLAB/Plant运行、父级放行或任何screen12结果。

## 修复内容

- 四个PowerShell入口（NOPLANT、FIRST、TAIL11、TAIL11 binder）统一验证原始JSON中的 deadline_utc 文本必须精确为 2026-10-24T17:01:00Z，再按 DateTimeOffset、DateTime、string 三种ConvertFrom-Json结果分别转换，最后比较固定UTC ticks。FIRST核对运行合同、release及release contract；TAIL11核对运行合同、tail合同、release及release contract；binder核对运行合同与tail release contract。运行前继续执行冻结的场景运行时间和退出缓冲门槛。
- FIRST与TAIL11 runner改为读取真实合同字段 algorithm_change.prediction_gradient_scaled_by_beta；不向合同添加重复字段。
- 保留已修复的C6目录三级repoRoot解析、TAIL11固定11场校验、C6阶段receipt命名和线程数1设置。B72历史证据继续使用其原有C5 schema与名称。
- 更新C6输入锁内本地源码SHA，并更新实验目录和本审查目录的source binding。69个绑定引用中17个属于本地C6源码并已刷新、核对；上游引用保留原锁定值。本次未批量重读DEV raw。

## 静态核对

- 4个C6 .ps1由PowerShell AST parser解析通过；7个合同、输入锁、source binding和synthetic fixture JSON解析通过。
- C6运行合同消费者的23个唯一路径均存在；C6输入锁消费者的43个唯一路径均存在；TAIL11 release contract消费者路径通过。
- NOPLANT/FIRST/TAIL11三入口的固定期望字段分别覆盖release contract要求的19、34、30个字段。
- 输入锁内8个本地源码绑定及其隔离冻结副本SHA一致；source binding的17个本地引用SHA一致；报告目录与实验目录source binding字节一致。
- MATLAB入口路径按C6工作目录向上三级解析到DL1018根目录。未启动任何MATLAB/Plant入口，未访问当前TEST raw/score，也未创建release、执行收据或尝试输出。
- 冻结的core、wrapper、MATLAB helper和Python kernel均保持任务书SHA。

## 诊断解释边界

C6 core保留的 stage1DelayedTermNorm(k)=0.01*norm(delayedOut.prediction_gradient,'fro') 是未乘beta的参考诊断值，不代表实际应用的C6 prediction项范数。实际C6 prediction更新为 rho*beta*g；审查raw事件时应按 beta × stage1DelayedTermNorm 重建对应范数，并以冻结的 delayed_prediction_step_candidate.m 核对。不得据此声称beta=1之后闭环轨迹不变，也不得把单步诊断外推为闭环收益。

## SHA-256

| 文件 | SHA-256 |
|---|---|
| prepare_c6_startup_ramp_v1.m | b6e143b4d01af476fc08ac50e53d9bec4b8c0665f314c2112f0d1faf2a5ceb6e |
| run_c6_startup_ramp_first_v1.m | aeec013bd2bf2d869f71b9b2318436d20ec53e85375adcea056ef10591605a99 |
| run_c6_startup_ramp_tail11_v1.m | 59ca3776d43a24f907d015b6f9bb92c48112d584cff1c41d66acc75ebc8e4504 |
| RUN_C6_NOPLANT_EXACT_v1.ps1 | 74a68376aa72a38db3933acfb2c14df3eeb8bc4345f76323595138b00b391ffc |
| RUN_C6_FIRST_EXACT_v1.ps1 | def8efef70757ba02bb2d405740e4ba7cd95320f8f9c76a7a182e5d2399287e9 |
| RUN_C6_TAIL11_EXACT_v1.ps1 | d89194200d07f1cdc06719e9f5159840eb9b6788f0cf22ff2abe1ede62836f13 |
| BIND_C6_TAIL11_AFTER_FIRST_v1.ps1 | dc3d4c7c159dc60090eebef9c1a4ee04ad6e3e80b3f02db1f84c8801dc183db9 |
| C6_STARTUP_RAMP_INPUT_LOCK_v1.json | 919de01ed9a111f24f4028b5436bdfa46d817f32c475bbf18e70b87d2eb37c06 |
| C6_SOURCE_BINDING_v1.json | dd834d6c354cc27f0493ce715a0dfe677d9e0ba574ddf899ececf0c2661eb964 |
| C6_STARTUP_RAMP_RUN_CONTRACT_v1.json | 6b75d40ff257d38a8aa6c9d7e1384dacbaee5b89d9a218a19bbe3037b7d7a463 |
| C6_TAIL11_PARENT_RELEASE_CONTRACT_v1.json | 9fb12fd6a37f545c9ca9f4144bc7fa13feed49a64049444c85626b9cf834fd8b |
| run_dl1018_closed_loop.m (frozen copy) | 48350037b66efe00301b138068f187c62cf92583f0f9ba2fabc9b24f248a963c |
| run_episode_dl1018.m (frozen copy) | fcc1f5de659541e692483f8395d93fd2a251256286ebade5e510ed4c7a2e2330 |
| delayed_prediction_step_candidate.m | 53e5c2fa8098769b84952c93469625eae9abedccb199a1c57d3746b8005bd067 |
| delayed_prediction_kernel.py | 0ad47c691f5411e36d75ab5f1f78ecb0a945564371ecfb2fc18066b47ae2bcac |

源码冻结仅表示静态入口和绑定已可审核。仍须由根审查并在未来明确放行后，才可考虑后续noPlant、首场及独立尾批阶段。