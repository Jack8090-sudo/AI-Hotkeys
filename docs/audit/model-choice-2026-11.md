# Model choice, November 2026: built-in LFM2.5-230M vs Gemma 4 E4B

Why AI-Hotkeys 1.2 ships its own small model, and what it costs in quality. Measured on an RTX 3060 12 GB
(Windows 11), 3 repetitions per case with the app's real sampling settings.

## The two engines

| | Built-in: LFM2.5-230M fine-tuned (`lfm-hotkeys-Q6_K.gguf`) | Ollama: Gemma 4 E4B QAT |
|---|---|---|
| To install | nothing (in the installer) | Ollama + `ollama pull` (about 6 GB) |
| Size on disk | 191 MB | about 6 GB |
| Memory while loaded | about 0.5 GB | 3-4 GB of VRAM |
| Load time | about 0.7 s | 10-20 s (up to a minute after a reboot) |
| Writing speed, GPU | about 500 tokens/s (Vulkan) | about 75 tokens/s |
| Writing speed, processor only | about 200 tokens/s | about 10 times slower than on the GPU |

## Quality (share of passed checks)

| Case set | Cases × 3 | LFM, base model | LFM fine-tuned | Gemma 4 E4B |
|---|---|---|---|---|
| App benchmark + development cases (`tools/bench/model_eval.py` + dev set) | 147 | about 19% (app set only) | **96%** | 97% |
| Held-out set (written after training, never used to choose data) | 60 | — | **88%** | 95% |
| End with real web sources (frozen) + follow-up questions | 39 | — | **77%** | 100% |

The base model mostly repeated the instructions or copied the text instead of summarizing it.

## How the model was made

1. **Directional weight editing** (diagnose with forward hooks, find the "copies instead of summarizing"
   direction, orthogonalize it out of the residual-writing matrices) did not help: the copy direction was
   clearly separable (Cohen's d 2.4 at layer 9), but removing it from every layer still left 65 of 66
   summaries copied, and adding the opposite direction broke the model before it changed the behavior.
   The base model did not have a defect to remove; it lacked the skill.
2. **Added weights.** The fix was a LoRA adapter (rank 32 on the attention, short-convolution and
   feed-forward layers), trained on 4,533 answers written by Gemma 4 12B/E4B with the app's own prompts and
   filtered by the same checks as the benchmark. Synthetic proofreading pairs (mistakes injected into correct
   Italian) cover accents, spelling and verb forms. The adapter is merged into the weights, then converted to
   GGUF and quantized to Q6_K (Q8_0 and Q4_K_M scored the same within noise; Q6_K is the safer middle).
3. The model is trained on short prompts without worked examples (`prompts_lfm.py`), so the prompt is short
   and fast to read.

## Where Gemma is still better

- Explanations built on long web pages: LFM sometimes repeats a line or forgets the `[n]` citations.
- Small factual slips in summaries (a wrong day) and, in fixes, an occasional change of a verb's person
  ("rispondevi" → "rispondevamo"). Rarely a fix drops a word that carries the meaning: in one of two runs
  "domani nn vengo" became "Domani vengo".
- Follow-up edits such as "make it a bulleted list".

Who wants the richest explanations and has the VRAM can switch the engine to Ollama in Settings.
