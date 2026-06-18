% spmx: DCM estimation template

matlabbatch{1}.spm.dcm.estimate.dcms.subj.dcmmat = {'%%DCM_MAT_PATH%%'};
matlabbatch{1}.spm.dcm.estimate.output.single.dir = {'%%OUTPUT_DIR%%'};
matlabbatch{1}.spm.dcm.estimate.output.single.name = '%%MODEL_NAME%%';
matlabbatch{1}.spm.dcm.estimate.est_type = 1;
matlabbatch{1}.spm.dcm.estimate.fmri.analysis = %%ANALYSIS_TYPE%%;

