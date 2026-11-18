# P1 sustained overload

`binary_sensor.p1_sustained_overload` is on when the highest raw P1
phase current has been at or above 27 A for 60 s. It stays on until
the load has been below 27 A for 60 min.

The Zaptec fuse guard ignores the optimiser's battery grid charge
while the optimiser is in control, because the optimiser holds the
highest phase at about 25.6 A and cuts the battery when load rises.
This sensor is the check that it did: 27 A for a minute means the
battery is not yielding, so the guard counts the battery as
household load again (the old behaviour). The 60 min delay off lets
the fuse cool down before the discount is tried again. The guard
keeps retrying after each quiet period by design; there is no latch.
`automations/zaptec/Overload_notify.yaml` sends a phone notification
every time the sensor turns on.

There is no availability template: an unavailable P1 reads 0 here,
and the guard's own P1 liveness check covers P1 loss. See
[the fuse guard docs](../automations/zaptec/README.md).
