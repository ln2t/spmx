% spmx: fMRI first-level GLM specification, estimation, contrasts, and results
% This template uses placeholder tokens (%%TOKEN%%) that are replaced by Python.

% =========================================================================
% Batch 1: fMRI model specification
% =========================================================================
matlabbatch{1}.spm.stats.fmri_spec.dir = {'%%OUTPUT_DIR%%'};
matlabbatch{1}.spm.stats.fmri_spec.timing.units = 'secs';
matlabbatch{1}.spm.stats.fmri_spec.timing.RT = %%TR%%;
matlabbatch{1}.spm.stats.fmri_spec.timing.fmri_t = %%FMRI_T%%;
matlabbatch{1}.spm.stats.fmri_spec.timing.fmri_t0 = %%FMRI_T0%%;
matlabbatch{1}.spm.stats.fmri_spec.sess.scans = {%%SCANS%%};
%%CONDITIONS%%
matlabbatch{1}.spm.stats.fmri_spec.sess.multi = {''};
%%REGRESSORS%%
matlabbatch{1}.spm.stats.fmri_spec.sess.multi_reg = {''};
matlabbatch{1}.spm.stats.fmri_spec.sess.hpf = %%HPF%%;
matlabbatch{1}.spm.stats.fmri_spec.fact = struct('name', {}, 'levels', {});
matlabbatch{1}.spm.stats.fmri_spec.bases.hrf.derivs = [0 0];
matlabbatch{1}.spm.stats.fmri_spec.volt = 1;
matlabbatch{1}.spm.stats.fmri_spec.global = 'None';
matlabbatch{1}.spm.stats.fmri_spec.mthresh = 0.8;
matlabbatch{1}.spm.stats.fmri_spec.mask = {%%MASK%%};
matlabbatch{1}.spm.stats.fmri_spec.cvi = 'AR(1)';

% =========================================================================
% Batch 2: Model estimation
% =========================================================================
matlabbatch{2}.spm.stats.fmri_est.spmmat(1) = cfg_dep('fMRI model specification: SPM.mat File', substruct('.','val', '{}',{1}, '.','val', '{}',{1}, '.','val', '{}',{1}), substruct('.','spmmat'));
matlabbatch{2}.spm.stats.fmri_est.write_residuals = %%WRITE_RESIDUALS%%;
matlabbatch{2}.spm.stats.fmri_est.method.Classical = 1;

% =========================================================================
% Batch 3: Contrast manager
% =========================================================================
matlabbatch{3}.spm.stats.con.spmmat(1) = cfg_dep('Model estimation: SPM.mat File', substruct('.','val', '{}',{2}, '.','val', '{}',{1}, '.','val', '{}',{1}), substruct('.','spmmat'));
%%CONTRASTS%%
matlabbatch{3}.spm.stats.con.delete = 0;

% =========================================================================
% Batch 4: Results report
% =========================================================================
matlabbatch{4}.spm.stats.results.spmmat(1) = cfg_dep('Contrast Manager: SPM.mat File', substruct('.','val', '{}',{3}, '.','val', '{}',{1}, '.','val', '{}',{1}), substruct('.','spmmat'));
%%RESULT_CONSPEC%%
matlabbatch{4}.spm.stats.results.units = 1;
matlabbatch{4}.spm.stats.results.export{1}.pdf = true;
matlabbatch{4}.spm.stats.results.export{2}.csv = true;
