# Target configs

One OpenOCD config per MCU family. Copy the closest one and adjust when your
target is not here.

| File | Part | Notes |
|---|---|---|
| `gd32f303.cfg` | GigaDevice GD32F303xx | STM32F103-compatible map, Cortex-M4, clone DAP IDCODE |
| `stm32f1x.cfg` | ST STM32F1xx | genuine ST part |

Every config here deliberately sets `reset_config none`. On a handheld radio the
debug header rarely has NRST wired, and the running application remaps the SWD
pins — so the working sequence is *put the radio in firmware-update mode, then
attach passively*. A reset drops it back into the application and kills the
connection.

When you add a config, record in `TARGET.md` which one worked and what the probe
reported (core string, IDCODE, RDP level, flash size).
