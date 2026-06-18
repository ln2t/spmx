% spmx: VOI extraction template
% One matlabbatch per VOI — this template is for a single VOI.
% VOI is defined as the intersection of a sphere with the brain mask.

matlabbatch{1}.spm.util.voi.spmmat = {'%%SPM_MAT_PATH%%'};
matlabbatch{1}.spm.util.voi.adjust = NaN;
matlabbatch{1}.spm.util.voi.session = %%SESSION_NUMBER%%;
matlabbatch{1}.spm.util.voi.name = '%%VOI_NAME%%';
% ROI 1: Spherical seed region
matlabbatch{1}.spm.util.voi.roi{1}.sphere.centre = [%%SPHERE_CENTRE%%];
matlabbatch{1}.spm.util.voi.roi{1}.sphere.radius = %%SPHERE_RADIUS%%;
matlabbatch{1}.spm.util.voi.roi{1}.sphere.move.fixed = 1;
% ROI 2: Brain mask
matlabbatch{1}.spm.util.voi.roi{2}.mask.image = {'%%MASK_PATH%%'};
matlabbatch{1}.spm.util.voi.roi{2}.mask.threshold = 0.5;
% Expression: intersection of sphere (i1) with mask (i2)
matlabbatch{1}.spm.util.voi.expression = 'i1&i2';
