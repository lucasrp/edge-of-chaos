# Criticality Detection Toolkit — Can We Measure Edge of Chaos?

## What It Is

A convergent body of mathematical methods — developed independently across 8+ disciplines — for detecting whether a system operates near a critical phase transition. The striking finding: physicists call it "correlation length," cardiologists call it "DFA scaling exponent," financial analysts call it "Hurst exponent," ML researchers call it "spectral radius" — but they're all measuring the same thing: **how far do correlations extend in the system?** At criticality, they all approach 1.0.

## Original Context

- **ArXiv 2601.22389** (2025): "Convergent Discovery of Critical Phenomena Mathematics Across Disciplines" — documents independent convergence across physics, cardiology, finance, ML, ecology, neuroscience, epidemiology, and distributed systems.
- **ArXiv 2410.02536** (2024): "Intelligence at the Edge of Chaos" — five complexity metrics (Lempel-Ziv, compression, Lyapunov, Krylov, Wolfram class) applied to cellular automata training data. Optimal AI performance in Class IV (complex+structured).
- **Toker et al. 2020** (Communications Biology): Chaos Decision Tree — practical pipeline combining permutation entropy, 0-1 test, and surrogate validation.
- **AIP Chaos 2017**: Avalanche criticality and edge-of-chaos criticality are DISTINCT. Don't necessarily co-occur. Different signatures.
- **McAteer et al. 2016** (Space Science Reviews): 25-year review of SOC numerical detection methods — correlations, complexity, critical quantities.

## The Toolkit (Five Families of Metrics)

### 1. Correlation Extent (the universal signal)
- **What it measures:** How far perturbations propagate
- **Critical indicator:** Parameter → 1.0
- **Variants:** DFA exponent α, Hurst exponent H, spectral radius χ, branching ratio σ, contraction factor κ_m
- **Practical:** Computable from any time series with ~10³+ data points

### 2. Compression-Based Detection
- **What it measures:** Structural complexity of sequences
- **How:** Apply GZIP/BZ2/LZMA at multiple scales
- **Signatures:** High compression = ordered (Class I/II), low compression = chaotic (Class III), moderate = edge of chaos (Class IV)
- **Practical:** Dead simple to compute, no domain expertise needed

### 3. Lyapunov Exponent (sensitivity to perturbation)
- **What it measures:** How fast nearby trajectories diverge
- **Critical indicator:** λ ≈ 0 (exactly at transition between ordered λ<0 and chaotic λ>0)
- **Practical:** Requires continuous time series, sensitive to noise

### 4. Power-Law Distribution (avalanche criticality)
- **What it measures:** Scale-free distribution of event sizes
- **Critical indicator:** P(s) ~ s^(-τ) with rigorous fit (p-value, xmin, likelihood ratio vs log-normal)
- **Practical:** Requires large event catalogs (10³+ events)
- **IMPORTANT:** Avalanche criticality ≠ edge-of-chaos criticality. Separate phenomena.

### 5. Permutation Entropy + 0-1 Test (chaos detection pipeline)
- **What it measures:** Whether dynamics are stochastic, periodic, or chaotic
- **How:** Permutation entropy classifies stochastic vs deterministic; 0-1 test yields K∈[0,1] (0=periodic, 1=chaotic)
- **Practical:** Robust to noise, works on short series (~500 points)

## Application to Our System

### Observable Time Series We Produce
1. Health scores over time (integer, sampled per beat)
2. Beat theme sequences (categorical → symbol string)
3. Claims accumulation (open vs closed, rate over time)
4. Repair event sizes and frequencies
5. Beat intervals (time between beats)

### Most Practical First Steps
**A. Branching ratio on beat outcomes:**
- σ = average follow-up items (claims, threads, insights) per beat
- σ ≈ 1.0 → critical (each insight generates ~1 new question)
- σ < 1.0 → subcritical (ideas die out)
- σ > 1.0 → supercritical (unbounded growth, unresolved claims pile up)

**B. Compression of beat theme sequences:**
- Encode themes as symbols, compress with gzip
- Track compression ratio over sliding windows
- Medium compression = structured but not repetitive

**C. Hurst exponent on health score series:**
- Needs ~100+ data points (we're approaching this)
- H→1.0 = long-range correlations (approaching criticality)

## The Identifiability Problem (CRITICAL CAVEAT)

**Adversarial review (GPT-5.4 + Grok-4) identified a fundamental weakness:**

Criticality statistics are ubiquitous and cheap to produce in systems with memory, aggregation, or hierarchical mixing. Measuring σ≈1, Hurst→1, or moderate compression does NOT prove criticality. It's consistent with:
- Autocorrelation from LLM memory
- Non-stationarity mimicking long-range dependence
- Editorial repetition patterns
- Aggregation artifacts

**What would constitute STRONG evidence:**
1. **Null models:** Compare against random beat sequences, shuffled themes, synthetic health scores
2. **Finite-size scaling:** Signature persists when varying observation window
3. **Prediction:** Being "closer to critical" correlates with measurable performance improvement
4. **Sensitivity analysis:** Results stable across different definitions of "beat outcome"

**What we should NOT claim:** "We operate at the edge of chaos because σ≈1"
**What we CAN claim:** "Here are tools to measure where we are on the order-chaos spectrum, with proper controls"

## Sources

- ArXiv 2601.22389v1 — Convergent Discovery of Critical Phenomena
- ArXiv 2410.02536v1 — Intelligence at the Edge of Chaos
- ArXiv 2107.09437 — Edge of Chaos as Guiding Principle for NN Training
- Toker et al. 2020 — Simple Method for Detecting Chaos (Communications Biology)
- AIP Chaos 27(4), 047408 (2017) — Avalanche and EoC Criticality Don't Co-occur
- McAteer et al. 2016 — 25 Years of SOC: Numerical Detection Methods (Space Science Reviews)
