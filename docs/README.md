# Technical Documentation Index

This folder contains detailed technical documentation for `spmx`. Use this index to find information about specific topics.

## Quick Navigation

### For First-Time Users
1. Start with [README.md](../README.md)
2. Review [Configuration Guide](configuration.md) for setup
3. See [Examples](../config_examples/) for realistic configurations

### For Pipeline developers
1. [MATLAB Templates & Script Generation](matlab_templates.md) — How scripts are created
2. [Advanced Topics](advanced_topics.md) — Implementation details

### For Data Analysis
1. [Output File Mapping](outputs.md) — What each output file represents
2. [DCM Specification](dcm_specification.md) — Deep dive into DCM models
3. [Configuration Guide](configuration.md) — Parameter reference

---

## Documentation Files

### [Configuration Guide](configuration.md)
**Audience**: Users setting up pipelines

Comprehensive reference for all configuration parameters:
- YAML configuration file structure
- Parameter descriptions and defaults
- Priority order (defaults → config → CLI)
- Common configuration patterns
- Best practices and tips

**When to use**:
- Setting up `--config` files
- Understanding parameter effects
- Troubleshooting configuration issues

---

### [Output File Mapping](outputs.md)
**Audience**: Users analyzing results

Details about all output files:
- What each output file represents
- BIDS file naming conventions
- JSON sidecar metadata
- Example output directory structure
- How to load and use outputs in MATLAB/Python

**When to use**:
- Understanding your processed data
- Loading outputs for analysis
- BIDS validation
- Downstream analysis setup

---

### [MATLAB Templates & Script Generation](matlab_templates.md)
**Audience**: Pipeline developers, advanced users

How the tool generates and runs MATLAB scripts:
- SPM batch system overview
- Template file structure and documentation
- Script generation workflow
- Data handling and file I/O
- Debugging generated scripts
- Performance considerations

**When to use**:
- Modifying template behavior
- Understanding MATLAB operations
- Debugging script generation
- Contributing to project

---

### [DCM Specification & Structure](dcm_specification.md)
**Audience**: Users fitting DCM models

Detailed guide to DCM specifications:
- DCM overview and terminology
- Connectivity matrices (A, B, C)
- Pre-defined and custom models
- Estimation options and parameters
- Resting-state vs. task-based DCM
- Output interpretation
- Limitations and assumptions

**When to use**:
- Setting up DCM models
- Understanding connectivity matrices
- Interpreting DCM results
- Troubleshooting model estimation

---

### [Advanced Topics & Implementation Details](advanced_topics.md)
**Audience**: Power users, developers

Deep technical information:
- BIDS compliance strategy
- Uncompressed NIFTI file handling
- SPM.mat file management
- Processing status tracking
- Batch and parallel processing strategies
- BIDS entity filters (participant, session, task, space)
- Event and confounds file processing
- Volume count determination
- Logging system
- Error handling and recovery
- Performance tuning

**When to use**:
- Understanding internal design
- Optimizing large-scale processing
- Handling edge cases
- Debugging pipeline issues
- Contributing to development

---

## Common Questions & Where to Find Answers

| Question | Document |
|----------|----------|
| How do I configure the pipeline? | [Configuration Guide](configuration.md) |
| What are the default parameter values? | [Configuration Guide](configuration.md) → Top-Level Settings |
| How do I define VOI seeds? | [Configuration Guide](configuration.md) → voi Section |
| How do I set up DCM models? | [DCM Specification](dcm_specification.md) or [Configuration Guide](configuration.md) → dcm Section |
| What are the output files and what do they mean? | [Output File Mapping](outputs.md) |
| How do I load and use the output files? | [Output File Mapping](outputs.md) → Using Output Files |
| How are MATLAB scripts generated? | [MATLAB Templates & Script Generation](matlab_templates.md) |
| Why are there uncompressed files in sourcedata/? | [Advanced Topics](advanced_topics.md) → Handling Uncompressed NIFTI Files |
| How do I process multiple subjects in parallel? | [Advanced Topics](advanced_topics.md) → Parallel Processing Strategy |
| How do I debug a failed run? | [Advanced Topics](advanced_topics.md) → Logging System & Error Handling |
| What are the performance characteristics? | [Advanced Topics](advanced_topics.md) → Performance Tuning |

---

## Reference by Processing Stage

### Fit Stage
1. Configuration: [Configuration Guide → fit Section](configuration.md#fit-section)
2. Implementation: [MATLAB Templates → fmri_fit.m](matlab_templates.md#fmri_fitm)
3. Outputs: [Output File Mapping → Fit Stage Outputs](outputs.md#fit-stage-outputs)
4. Technical details: [Advanced Topics → Event & Confounds Processing](advanced_topics.md#event-file-processing-task-based)

### VOI Stage
1. Configuration: [Configuration Guide → voi Section](configuration.md#voi-section)
2. Implementation: [MATLAB Templates → fmri_voi.m](matlab_templates.md#fmri_voim)
3. Outputs: [Output File Mapping → VOI Stage Outputs](outputs.md#voi-stage-outputs)
4. Algorithm: [DCM Specification → Pre-defined Models](dcm_specification.md)

### DCM Stage
1. Configuration: [Configuration Guide → dcm Section](configuration.md#dcm-section)
2. Specification: [DCM Specification](dcm_specification.md)
3. Implementation: [MATLAB Templates → fmri_dcm_estimate.m](matlab_templates.md#fmri_dcm_estimatem)
4. Outputs: [Output File Mapping → DCM Stage Outputs](outputs.md#dcm-stage-outputs)

---

## File Formats & Standards

### BIDS Compliance
- Main README section: [Output Format](../README.md#output-format)
- Detailed mapping: [Output File Mapping](outputs.md)
- Technical details: [Advanced Topics → BIDS Compliance Strategy](advanced_topics.md#bids-compliance-strategy)

### JSON Sidecars
- Overview: [Output File Mapping → JSON Sidecars](outputs.md#json-sidecars)
- Metadata fields: Examples in [Output File Mapping](outputs.md)

### MATLAB Files (VOI, DCM)
- Loading in Python: [Output File Mapping → Using Output Files](outputs.md#load-voi-timeseries-in-python)
- Loading in MATLAB: [Output File Mapping → Using Output Files](outputs.md#load-voi-timeseries-in-matlab)

---

## Troubleshooting Guide

**Problem**: Pipeline fails; can't understand why
- **Step 1**: Check error messages in `OUTPUT_DIR/logs/`
- **Step 2**: Re-run with `--debug` flag to get detailed logs
- **Step 3**: Look at generated MATLAB scripts in `OUTPUT_DIR/logs/sub-*/matlab_scripts/`
- **Reference**: [Advanced Topics → Error Handling & Recovery](advanced_topics.md#error-handling--recovery)

**Problem**: Output files have unexpected names
- **Reference**: [Output File Mapping](outputs.md) for BIDS naming conventions
- **Reference**: [Configuration Guide](configuration.md) for DESC field control

**Problem**: DCM estimation fails or produces unexpected results
- **Step 1**: Verify VOI extraction succeeded (check VOI .mat files exist)
- **Step 2**: Review DCM model specification in config
- **Reference**: [DCM Specification](dcm_specification.md) for matrix definitions
- **Reference**: [Configuration Guide → dcm Section](configuration.md#dcm-section)

**Problem**: Can't find confounds or events file data
- **Reference**: [Advanced Topics → Event File Processing](advanced_topics.md#event-file-processing-task-based)
- **Reference**: [Advanced Topics → Confounds File Processing](advanced_topics.md#confounds-file-processing)

---

## Contributing

To improve documentation:

1. **Report issues**: GitHub Issues with documentation tag
2. **Suggest updates**: Submit PR with changes and rationale
3. **Add examples**: Share configurations and use cases

---

## Related Resources

- **Main README**: [../README.md](../README.md)
- **Examples**: [../config_examples/](../config_examples/)
- **Source Code**: [spmx/](../spmx/)
- **SPM Documentation**: https://www.fil.ion.ucl.ac.uk/spm/doc/
- **BIDS Standard**: https://bids-standard.github.io/
