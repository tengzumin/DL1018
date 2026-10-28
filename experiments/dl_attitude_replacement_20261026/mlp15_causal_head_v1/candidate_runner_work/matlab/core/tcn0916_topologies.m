function [names,arms] = tcn0916_topologies()
%TCN0916_TOPOLOGIES The complete 16-cell TCN0916 ID morphology set.
    names = {'C0','1','2','3','4','12','23','34','14','13','24', ...
        '123','124','134','234','1234'};
    arms = {[],1,2,3,4,[1 2],[2 3],[3 4],[1 4],[1 3],[2 4], ...
        [1 2 3],[1 2 4],[1 3 4],[2 3 4],[1 2 3 4]};
end
