# MoMaHub Demo — Prof. Lu Jianping, UNC Chapel Hill

**Topic:** Distributed AI Inference & eta_AI (bits/joule)

## Prerequisites

```bash
# Start hub on one machine
moma hub up --host 0.0.0.0 --port 8000

# Join 3 agents (on each GTX 1080 Ti machine)
moma join http://<hub-ip>:8000 --name alice
moma join http://<hub-ip>:8000 --name bob
moma join http://<hub-ip>:8000 --name charlie
```

## Demo Steps

| Step | Name | What it does |
|------|------|-------------|
| 0 | Grid Status | Show agents, tiers, GPUs |
| 1 | Stress Test | 15 tasks fan-out, throughput numbers |
| 2 | Model Arena | Same entropy/eta_AI question to 3 models |
| 3 | Chain Relay | 3-step reasoning about "eta_AI: bits per joule" |
| 4 | Batch Translate | Translate an eta_AI description into 5 languages |
| 5 | eta_AI Discussion | The physics: Landauer limit, comparison table, experiment sketch |

## Usage

```bash
# Interactive — step by step with confirmations
python demo.py

# Run a single step
python demo.py --step 3

# Run everything straight through
python demo.py --all

# Custom hub / model
python demo.py --hub http://192.168.1.10:8000 --model mistral
```

## eta_AI: Bits per Joule

The proposed efficiency metric:

```
eta_AI = generated_bits / energy_joules
       = (output_tokens * bits_per_token) / (watts * seconds)
```

Where:
- **output_tokens** — from Ollama `eval_count`
- **bits_per_token** — ~10-12 bits (log2 of vocab size, adjusted for entropy)
- **watts** — GPU power draw via `nvidia-smi`
- **seconds** — `eval_duration` from Ollama

### Comparison Table

| System | Throughput | Power | eta_AI (bits/joule) |
|--------|-----------|-------|-------------------|
| GTX 1080 Ti (llama3:8b) | ~40 tokens/s | ~200W | ~2.2 |
| A100 (llama3:8b) | ~100 tokens/s | ~300W | ~3.7 |
| Human brain | ~10^13 bits/s | ~20W | ~5 x 10^11 |
| Landauer limit (300K) | theoretical | kT ln(2) | ~3 x 10^21 |

The gap between current GPUs and Landauer's limit is **~21 orders of magnitude**.

### Experiment Sketch

1. Run stress test with `nvidia-smi` logging power draw (1s interval)
2. Correlate total tokens generated with total energy consumed
3. Vary: model size, batch size, quantization level
4. Plot eta_AI vs model_size — does a scaling law hold for efficiency?

---

## Appendix:

### What is Landauer's Principle?

In 1961, Rolf Landauer (IBM) proved that **erasing one bit of information must dissipate a minimum amount of energy** as heat:

```
E_min = kT * ln(2)
```

- **k** = Boltzmann constant (1.38 x 10^-23 J/K)
- **T** = temperature in Kelvin
- **ln(2)** = 0.693

At room temperature (300K):

```
E_min = 1.38e-23 * 300 * 0.693 = 2.87 x 10^-21 joules per bit
```

### Why it matters

**It connects physics to information.** You can compute for free (in principle), but the moment you *erase* or *overwrite* a bit -- which every real computation does constantly -- thermodynamics demands a minimum energy cost. It is not an engineering limit; it is a law of nature, like the speed of light.

Inverting it gives the theoretical maximum efficiency:

```
eta_max = 1 / E_min = 1 / (kT * ln(2)) = 3.5 x 10^20 bits/joule at 300K
```

No computer, no matter how advanced, can exceed this.

### The 21-order-of-magnitude gap

| System | eta_AI (bits/joule) | Gap from Landauer |
|--------|-------------------|-------------------|
| GTX 1080 Ti | ~2.2 | 10^20x below |
| A100 | ~3.7 | 10^20x below |
| Human brain | ~5 x 10^11 | 10^9x below |
| Landauer limit | ~3.5 x 10^20 | -- |

Even the human brain is a billion times less efficient than the theoretical limit. GPUs are another 10^11x worse than the brain.

### The deep insight

Landauer's principle means **information is physical**. Erasing a bit is an irreversible thermodynamic process -- it increases the entropy of the universe. This is why GPUs get hot: every token generated involves billions of bit erasures, each paying the thermodynamic tax.

The question "how many bits of useful information can an LLM produce per joule?" (eta_AI) is really asking: **how far is AI inference from the fundamental physical limit of computation?** That is a question that sits at the intersection of statistical mechanics, information theory, and AI -- exactly the kind of cross-disciplinary inquiry that makes for a compelling physics experiment.
