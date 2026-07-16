## Extended Results

The paper reports aggregate results across all trap scenarios. The tables below provide additional breakdowns by topology family and trap type.

Metric definitions:

| Metric                   | Meaning                                                                                          |
| ------------------------ | ------------------------------------------------------------------------------------------------ |
| Mission Success          | Trial inspects the target, preserves the battery safety floor, and terminates at a recovery node |
| Target Inspected         | Trial inspects the target regardless of final recovery status                                    |
| Battery Depletion        | Battery reaches zero                                                                             |
| Battery Safety Violation | Trial ends below the configured battery safety floor                                             |
| Fallback Calls           | Average number of planner/reasoning fallback invocations per trial                               |
| Execution Cost           | Battery-equivalent cost accumulated over movement, inspection, waiting, and fallback overhead    |

### Results by Topology Family

| Scenario         | Policy           | Mission Success (%) | Target Inspected (%) | Battery Depletion (%) | Safety Violation (%) | Fallback Calls | Execution Cost |
| ---------------- | ---------------- | ------------------: | -------------------: | --------------------: | -------------------: | -------------: | -------------: |
| Linear Corridor  | Top-1 Reuse      |                37.2 |                 84.1 |                  15.9 |                 62.8 |           0.00 |          32.70 |
|                  | Threshold Reuse  |                37.8 |                 84.2 |                  14.8 |                 62.2 |           0.02 |          32.62 |
|                  | Always Reasoning |                83.9 |                 99.4 |                   2.2 |                 16.1 |          16.77 |          58.83 |
|                  | MemoGuard        |                83.1 |                 98.7 |                   2.2 |                 16.9 |          13.13 |          55.97 |
| Alternate Path   | Top-1 Reuse      |                27.7 |                 79.6 |                  24.8 |                 72.3 |           0.00 |          39.22 |
|                  | Threshold Reuse  |                27.2 |                 67.4 |                  26.7 |                 72.4 |           1.48 |          40.16 |
|                  | Always Reasoning |                85.1 |                 97.7 |                   1.9 |                 14.9 |          18.52 |          63.25 |
|                  | MemoGuard        |                84.1 |                 97.1 |                   1.9 |                 15.9 |          15.11 |          61.27 |
| Long Return Cost | Top-1 Reuse      |                32.9 |                 77.6 |                  15.9 |                 67.1 |           0.00 |          38.20 |
|                  | Threshold Reuse  |                33.3 |                 78.5 |                  15.2 |                 66.7 |           0.07 |          38.41 |
|                  | Always Reasoning |                81.5 |                 98.7 |                   2.5 |                 18.5 |          20.41 |          66.93 |
|                  | MemoGuard        |                85.3 |                 98.9 |                   2.0 |                 14.7 |          15.55 |          63.31 |
| Average          | Top-1 Reuse      |                32.6 |                 80.4 |                  18.9 |                 67.4 |           0.00 |          36.71 |
|                  | Threshold Reuse  |                32.8 |                 76.7 |                  18.9 |                 67.1 |           0.52 |          37.06 |
|                  | Always Reasoning |                83.5 |                 98.6 |                   2.2 |                 16.5 |          18.57 |          63.00 |
|                  | MemoGuard        |                84.2 |                 98.2 |                   2.0 |                 15.8 |          14.60 |          60.18 |

### Results by Trap Type

| Trap Type            | Policy           | Mission Success (%) | Target Inspected (%) | Battery Depletion (%) | Safety Violation (%) | Fallback Calls | Execution Cost |
| -------------------- | ---------------- | ------------------: | -------------------: | --------------------: | -------------------: | -------------: | -------------: |
| Block Edges          | Top-1 Reuse      |                55.7 |                 93.8 |                  13.6 |                 44.3 |           0.00 |          40.52 |
|                      | Threshold Reuse  |                56.4 |                 91.9 |                  12.0 |                 43.6 |           0.78 |          40.99 |
|                      | Always Reasoning |                85.0 |                 99.1 |                   2.2 |                 15.0 |          17.47 |          62.56 |
|                      | MemoGuard        |                87.0 |                 98.9 |                   1.9 |                 13.0 |          13.51 |          59.66 |
| Reduce Battery       | Top-1 Reuse      |                13.2 |                 95.7 |                  18.4 |                 86.8 |           0.00 |          36.80 |
|                      | Threshold Reuse  |                13.2 |                 90.5 |                  18.1 |                 86.8 |           0.43 |          37.11 |
|                      | Always Reasoning |                82.1 |                 97.5 |                   2.1 |                 17.9 |          19.99 |          62.07 |
|                      | MemoGuard        |                79.9 |                 96.8 |                   2.4 |                 20.1 |          14.94 |          58.75 |
| Remove Alt Viewpoint | Top-1 Reuse      |                28.8 |                 51.8 |                  24.7 |                 71.2 |           0.00 |          32.88 |
|                      | Threshold Reuse  |                28.6 |                 47.5 |                  26.7 |                 70.9 |           0.38 |          33.17 |
|                      | Always Reasoning |                83.5 |                 99.2 |                   2.3 |                 16.5 |          18.28 |          64.45 |
|                      | MemoGuard        |                85.6 |                 99.1 |                   1.7 |                 14.4 |          15.37 |          62.20 |
| Average              | Top-1 Reuse      |                32.6 |                 80.4 |                  18.9 |                 67.4 |           0.00 |          36.73 |
|                      | Threshold Reuse  |                32.7 |                 76.6 |                  18.9 |                 67.1 |           0.53 |          37.09 |
|                      | Always Reasoning |                83.5 |                 98.6 |                   2.2 |                 16.5 |          18.58 |          63.03 |
|                      | MemoGuard        |                84.2 |                 98.2 |                   2.0 |                 15.8 |          14.60 |          60.21 |
