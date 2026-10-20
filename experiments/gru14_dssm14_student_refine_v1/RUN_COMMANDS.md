# 运行命令

在 DL1018 项目根目录执行。每一步会复用已完成的轨迹/检查点；启动前先确认同阶段没有活动进程。

```powershell
python experiments/gru14_dssm14_student_refine_v1/scripts/refine.py collect
python experiments/gru14_dssm14_student_refine_v1/scripts/refine.py train
python experiments/gru14_dssm14_student_refine_v1/scripts/refine.py export
python experiments/gru14_dssm14_student_refine_v1/scripts/refine.py canary
python experiments/gru14_dssm14_student_refine_v1/scripts/refine.py dev
python experiments/gru14_dssm14_student_refine_v1/scripts/refine.py report
```

`canary` 完成 BRIDGE6 后按冻结门槛锁定四个包；`dev` 会先要求锁定文件存在，再跑满四组各 24 场。禁止在此任务中访问 TEST。
