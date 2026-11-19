# P1 sustained overload

`binary_sensor.p1_sustained_overload` is on when the highest raw P1
phase current has been at or above 27 A for 60 s (`delay_on`). It
stays on until the load has been below 27 A for 60 min
(`delay_off`).

27 A sits above the level the optimiser settles at, so a minute
there means the battery is not yielding. The 60 min `delay_off` lets
the fuse cool down before the guard tries the battery discount
again. Why the guard needs the check, and why it retries without a
latch, is in [the fuse guard docs](../automations/zaptec/README.md).

There is no availability template: an unavailable P1 reads 0 here,
and the guard's own P1 liveness check covers P1 loss.
