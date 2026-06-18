# PEB Results Extraction - Data Processing Options

This document summarizes the optional data processing steps that could be implemented in the PEB results extraction pipeline. These were identified from the original MATLAB script but are NOT yet implemented.

## Current Implementation

The current extract_peb_results.py module exports:
- **Ep** (expected values/parameter estimates) - as TSV vector
- **Cp** (covariance) - as TSV matrix  
- **Eg** (group effects) - as TSV vector
- **Metadata** - summary of analysis structure

All data is exported **as-is** without additional processing.

---

## Optional Data Processing Steps

### 1. **Parameter Matrix Reshaping** ⭐ (Most Complex)

**What it does:**
Converts the flat Ep/Eg/Pp vectors into interpretable matrix form (ROI × ROI for A/B, ROI × 1 for C).

**Current state:** The original MATLAB script computes parameter indices to extract submatrices:
```matlab
% For A matrix: ROI x ROI parameters
rr = (covar - 1) * ((Anum + Bnum) * (ROInum^2) + Cnum * ROInum) + (matrix - 1) * (ROInum^2);

% For C matrix: ROI x 1 parameters  
rr = (covar - 1) * ((Anum + Bnum) * (ROInum^2) + Cnum * ROInum) + (Anum + Bnum) * (ROInum^2) + (matrix - Anum - Bnum - 1) * ROInum;
```

**Would provide:**
- Per-covariate A matrix estimates
- Per-covariate B matrix estimates (if applicable)
- Per-covariate C matrix estimates (inputs)
- Clear ROI → ROI connectivity maps

**Complexity:** Medium-High
- Requires understanding the PEB parameter layout
- Different for CSD (resting-state) vs. task-based analysis
- Needs ROI counts to reshape correctly

---

### 2. **Posterior Probability/Confidence Extraction**

**What it does:**
Extracts posterior probability (Pp) - the probability that each parameter is different from 0.

**Current state:** The original MATLAB script exports both:
- Estimates (Ep)
- Probabilities (Pp)

**Would provide:**
- Significance/confidence scores for each parameter
- Can be used to filter results (e.g., only keep Pp > 0.95)
- Different from classical p-values (Bayesian approach)

**Complexity:** Low
- Simple extraction like Ep
- Just need to check if Pp is available in xPEB structure
- Creates similar TSV files but with probability values

---

### 3. **Covariate Effect Scaling & Interpretation**

**What it does:**
Standardizes coefficients and provides effect sizes for each covariate.

**Implementation needed:**
- Z-score normalization of covariate effects
- Effect size computation (e.g., variance explained)
- Statistical summaries per covariate

**Would provide:**
- Directly comparable effect sizes across covariates
- Which covariates have strongest effects on connectivity

**Complexity:** Low
- Standard statistical transformations
- Only requires Ep and Cp (covariance for uncertainty intervals)

---

### 4. **Posterior Credible Intervals**

**What it does:**
Computes 95% credible intervals for parameters from the posterior covariance (Cp).

**Implementation:**
```python
std_error = np.sqrt(np.diag(Cp))
ci_lower = Ep - 1.96 * std_error
ci_upper = Ep + 1.96 * std_error
```

**Would provide:**
- Uncertainty quantification for each parameter
- Confidence bounds for publication
- Comparison with null hypothesis (if CI doesn't include 0)

**Complexity:** Low
- Just matrix operations
- Enhances the Ep export with uncertainty information

---

### 5. **Comparison Matrices (Between Covariates)**

**What it does:**
For categorical covariates, compute the difference matrices between factor levels.

**Example (resting-state, 2 groups):**
- A_patient_vs_control = A_estimates[patient] - A_estimates[control]
- Shows differential connectivity patterns by group

**Would provide:**
- Direct visualization of group differences
- ROI × ROI difference maps
- More interpretable than raw coefficients

**Complexity:** Medium
- Requires identifying categorical variables
- Needs proper reference coding interpretation
- Multiple comparison matrices if many covariates

---

## Recommended Roadmap

### Phase 1 (Current) ✅
- Basic extraction: Ep, Cp, Eg as TSV
- Metadata summary

### Phase 2 (Recommended Next) 🎯
- Add **Posterior Probability/Confidence** (low complexity, high value)
- Add **Posterior Credible Intervals** (low complexity, essential for publication)
- Clean documentation

### Phase 3 (Advanced)
- **Parameter Matrix Reshaping** (enables connectivity visualization)
- Covariate effect size computation

### Phase 4 (Specialized)
- Comparison matrices between factor levels
- Statistical summaries per covariate

---

## Implementation Notes

### xPEB Structure
The actual xPEB structure needs verification. Based on SPM documentation:
```matlab
xPEB.Ep       % Posterior expected value (group-level parameters)
xPEB.Cp       % Posterior covariance
xPEB.Eg       % Expected group effects
xPEB.Pp       % Posterior probability (if available)
xPEB.Xnames   % Covariate names
xPEB.DCM      % Original DCM structure with ROI names
```

### Data Type Handling
- MATLAB matrices may be saved as 2D or flattened depending on SPM version
- Need to handle both direct access (xPEB.Ep) and dict access (xPEB['Ep'])
- Row vs. column vector conventions

---

## Questions for User

1. **Which processing steps are most important for your use case?**
   - Just raw estimates (current)?
   - Plus credible intervals?
   - Full matrix reshaping for visualization?

2. **For parameter matrix reshaping:**
   - Do you want separate TSV files per covariate (simpler)?
   - Or one comprehensive matrix export?

3. **For probabilities:**
   - Include if available?
   - Apply confidence threshold for filtering?

Let me know your preferences and I can implement the desired features!
