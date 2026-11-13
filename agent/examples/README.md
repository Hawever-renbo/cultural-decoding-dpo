# Examples

`synthetic_interview.txt` is a **synthetic** interview written for this repository (two fictional night-market vendors talking about mobile payments). It is not research data and no real person said these words. It exists so that the agent can be run end to end without any copyrighted or confidential material.

Suggested focus: `How night-market food vendors decide whether to accept mobile payments`

```
python -m anthro_agent code -f examples/synthetic_interview.txt \
  --focus "How night-market food vendors decide whether to accept mobile payments"
```

The interview studies behind the training data, and the complete cases held out for evaluation, are not in this repository (see the top-level README, "What is not here").
