### tune on realAWSCloudwatch -> test on realKnownCause

| Detector | Threshold | Tune F1 | Windows detected | Recall | Alerts | Precision | F1 | Median delay | Points/s |
|---|---|---|---|---|---|---|---|---|---|
| rolling z-score | 7.0 | 0.384 | 8/18 | 0.444 | 24 | 0.375 | 0.407 | 0.667 | 1,497,490 |
| EWMA control chart | 7.0 | 0.317 | 7/18 | 0.389 | 28 | 0.286 | 0.329 | 0.667 | 3,073,717 |
| rolling median / MAD | 5.0 | 0.299 | 10/18 | 0.556 | 135 | 0.096 | 0.164 | 0.5 | 11,232 |
| seasonal profile (weekday x hour) | 10.0 | 0.254 | 15/18 | 0.833 | 123 | 0.163 | 0.272 | 0.379 | 377,555 |
| ensemble (median of 4) | 7.0 | 0.326 | 8/18 | 0.444 | 47 | 0.191 | 0.268 | 0.667 | 8,806 |

### tune on realKnownCause -> test on realAWSCloudwatch

| Detector | Threshold | Tune F1 | Windows detected | Recall | Alerts | Precision | F1 | Median delay | Points/s |
|---|---|---|---|---|---|---|---|---|---|
| rolling z-score | 7.0 | 0.407 | 20/30 | 0.667 | 104 | 0.269 | 0.384 | 0.5 | 604,817 |
| EWMA control chart | 7.0 | 0.329 | 21/30 | 0.7 | 117 | 0.205 | 0.317 | 0.5 | 992,244 |
| rolling median / MAD | 3.0 | 0.216 | 29/30 | 0.967 | 702 | 0.141 | 0.246 | 0.191 | 7,928 |
| seasonal profile (weekday x hour) | 12.0 | 0.294 | 26/30 | 0.867 | 507 | 0.148 | 0.253 | 0.31 | 283,712 |
| ensemble (median of 4) | 10.0 | 0.359 | 16/30 | 0.533 | 165 | 0.212 | 0.304 | 0.5 | 6,369 |
