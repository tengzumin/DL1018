function [event,phase,dtUpdate,lastEventTime] = rbf_event_scheduler_step(phase,rateHz,dt,timeNow,lastEventTime)
    % FUNCTION:
    %   按指定更新频率推进 RBF 事件调度器的相位累积器。
    % PURPOSE:
    %   在主仿真步长与学习更新频率不整除时仍保持因果的分数频率采样。
    % INPUT: phase 为无量纲相位；rateHz 为更新频率（Hz）；dt/timeNow/lastEventTime 均以秒计。
    % OUTPUT: event 指示当前是否触发更新；phase 为剩余相位；dtUpdate 为两次事件间隔；lastEventTime 更新为本次事件时间。
    %RBF_EVENT_SCHEDULER_STEP Advance a causal fractional-rate event scheduler.
    assert(rateHz > 0 && rateHz <= 1 / dt,'TCN0910:RbfSchedulerRate','Rate must be in (0,1/dt].');
    phase = phase + rateHz * dt;
    event = false;
    dtUpdate = 0;
    if phase >= 1 - 1e-12
        phase = phase - 1;
        event = true;
        dtUpdate = timeNow - lastEventTime;
        assert(dtUpdate > 0,'TCN0910:RbfSchedulerDt','Event interval must be positive.');
        lastEventTime = timeNow;
    end
end
