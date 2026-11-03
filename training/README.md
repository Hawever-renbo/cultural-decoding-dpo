# Training

DPO on the Z6 pairs, in progress. Each run is added here as it goes: config first, then metrics, then evaluation.

## Layout

```
training/
  runs/
    _template/          copy this for a new run
    <date>_<short-name>/
      README.md         what changed vs. the previous run, and why; results when done
      config.yaml       base model, objective, beta, lr, epochs, batch, max lengths, data filter
      metrics.csv       step, loss, rewards/chosen, rewards/rejected, reward margin, reward accuracy, mean output length
      eval.md           held-out pair accuracy; length check; sample generations
```

## Data used

- The main file: 8,021 pairs. The 172 flagged pairs are not used.
- Split pairs for evaluation by **paper**, not by pair. Units from the same paper share a context card, so a pair-level split leaks.

## Things to watch

These follow from [`../data/README.md`](../data/README.md):
- **Length.** Deep-reading and control pairs reward the longer side. Log the mean length of generated outputs per checkpoint, and compare plain DPO with a length-normalised objective (SimPO or R-DPO) if outputs grow.
- **Type balance.** Report reward accuracy per type (deep reading, emphasis, defect, control) and per defect label. A model can look good overall while learning only the easy defects.
- **The real target.** Reward accuracy on held-out pairs is a proxy. The project's evaluation is blind expert review of model codings on held-out complete cases. Those cases are never used in training or in data generation.

## Do not commit

Model weights, optimizer states, the full pair files, and any API keys. [`.gitignore`](../.gitignore) blocks the common ones.
