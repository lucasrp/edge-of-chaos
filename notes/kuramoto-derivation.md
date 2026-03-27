# Kuramoto Model — Mean-Field Derivation

## The Setup

N oscillators, each with phase theta_i and natural frequency omega_i:

    dtheta_i/dt = omega_i + (K/N) * sum_{j=1}^{N} sin(theta_j - theta_i)

Frequencies drawn from a distribution g(omega). Question: when does synchronization emerge?

## The Mean-Field Trick

Define the complex order parameter:

    r * e^{i*psi} = (1/N) * sum_{j=1}^{N} e^{i*theta_j}

r measures coherence (0 = uniform, 1 = perfect sync), psi is the mean phase.

Multiply both sides by e^{-i*theta_i} and take imaginary part:

    (K/N) * sum_j sin(theta_j - theta_i) = K * r * sin(psi - theta_i)

So each oscillator only sees the mean field, not individual neighbors:

    dtheta_i/dt = omega_i + K * r * sin(psi - theta_i)

This is the beautiful simplification — a global coupling reduces to each oscillator
being pulled toward the mean phase psi with strength K*r.

## Self-Consistency for the Lorentzian

In the rotating frame at psi (WLOG psi = 0), a locked oscillator satisfies:

    0 = omega_i + K * r * sin(-theta_i)
    => sin(theta_i) = omega_i / (K*r)

This has solutions only for |omega_i| < K*r. Oscillators with |omega| > K*r drift.

For the locked population, the contribution to r is:

    r = integral_{-K*r}^{K*r} cos(theta(omega)) * g(omega) d_omega

where cos(theta) = sqrt(1 - (omega/(Kr))^2).

For the Lorentzian (Cauchy) distribution:

    g(omega) = (gamma/pi) / (omega^2 + gamma^2)

Substituting u = omega/(Kr):

    r = Kr * integral_{-1}^{1} sqrt(1 - u^2) * g(Kr*u) du

For r != 0, divide both sides by r:

    1 = K * integral_{-1}^{1} sqrt(1 - u^2) * g(Kr*u) du

At the onset (r -> 0+), g(Kr*u) -> g(0):

    1 = K_c * g(0) * integral_{-1}^{1} sqrt(1 - u^2) du
      = K_c * g(0) * pi/2

So: **K_c = 2 / (pi * g(0))**

For Lorentzian: g(0) = 1/(pi*gamma), therefore:

    **K_c = 2*gamma**

## Order Parameter Above K_c

For the Lorentzian, the self-consistency equation can be solved exactly:

    r = sqrt(1 - K_c/K)    for K > K_c

This is a supercritical pitchfork bifurcation — r grows continuously from 0
as sqrt(K - K_c), the classic mean-field critical exponent beta = 1/2.

## Why This Matters

The Kuramoto transition is a paradigm for how:
- **Consensus emerges from diversity** — oscillators don't need to be identical
- **Critical thresholds exist** — below K_c, coupling has essentially no effect
- **Mean-field reduction works** — each agent only needs to perceive the collective
- **The transition is sharp but continuous** — not a switch, but a phase transition

For multi-agent systems: agents don't need to coordinate pairwise. If they can
perceive and respond to a collective signal (the order parameter), synchronization
emerges when coupling exceeds a threshold that depends on the diversity of the population.
