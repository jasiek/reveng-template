# Naming conventions — the living glossary

**Driver-owned, read-only to subagents.** Regenerate the "in use" column each wave from the names
actually in the program (`search_functions` per prefix, or `tools/verify_wave.py --glossary`) so
it cannot drift from the artifact it describes. Paste the in-use list into every subagent prompt.

## Rules

- Valid C identifiers. **PascalCase**, `Category_Action`, under 40 characters.
- One prefix per subsystem — pick the winner early and never let a synonym in
  (`Storage_` *or* `Nvm_` *or* `Flash_`, not all three; `UI_` *or* `Ui_`, not both).
- SRAM globals: `g_` prefix. Hungarian type prefix after it if you intend to script the typing
  pass (`g_dwTxFreq`, `g_bMuteFlag`, `g_aChannelName`) — the type then follows from the name and
  costs zero agent tokens to apply.
- Local labels inside a function: leave them; only entry points get names.
- Never rename a non-`FUN_` function. If an existing name is wrong, log a conflict.

## Starting vocabulary for a handheld transceiver

Adopt what fits, delete what does not, add what the target actually has. Record the decision here
the first time a prefix is used.

| Prefix | Domain | In use |
|---|---|---|
| `OS_` | RTOS kernel (uC/OS-II, FreeRTOS) — tasks, semaphores, mboxes, tick | |
| `Lcd_`, `Ui_`, `Menu_`, `Font_`, `Icon_` | display driver, screen/menu logic, glyphs | |
| `Key_`, `Enc_` | keypad scan, rotary encoder, side buttons, PTT | |
| `Codeplug_`, `Nvm_`, `Flash_`, `Eeprom_`, `Storage_` | persistent config + external memory | |
| `Ch_`, `Zone_`, `Contact_`, `Grp_`, `Scan_` | codeplug record types | |
| `Radio_`, `RF_`, `Pll_`, `Vco_`, `Pa_`, `Sql_` | RF path, synthesiser, PA control, squelch | |
| `Dmr_`, `Tdma_`, `Bptc_`, `Golay_`, `Rs_`, `Crc_` | DMR/TDMA framing and FEC | |
| `Ambe_`, `Vocoder_`, `Codec2_` | vocoder / codec interface | |
| `Ctcss_`, `Dcs_`, `Tone_`, `Dtmf_`, `Beep_` | analog signalling and alerts | |
| `Audio_`, `SoundEngine_`, `Amp_`, `Mic_` | audio routing, amplifier, mic AGC | |
| `Gps_`, `Aprs_`, `Ax25_`, `Nmea_` | location and packet | |
| `Bt_`, `Ble_` | Bluetooth module | |
| `Comm_`, `Cps_`, `Cmd_` | host/CPS serial protocol, command dispatch | |
| `Usb_`, `Cdc_`, `Dfu_` | USB stack and update mode | |
| `Adc_`, `Dac_`, `Tim_`, `Gpio_`, `Reg_`, `Rcc_`, `Usart_`, `Spi_`, `I2c_`, `Dma_`, `Pwr_` | MCU peripherals | |
| `Aes_`, `Rc4_`, `Des_`, `Rng_`, `Hash_` | crypto primitives | |
| `Batt_`, `Chg_`, `Temp_`, `Led_`, `Vibr_` | power, charging, indicators | |
| `Str_`, `Mem_`, `Bit_`, `Bcd_`, `Time_`, `Math_`, `Libc_` | library-grade helpers | |

## Confidence tags

| Tag | Means | Typical evidence |
|---|---|---|
| `HIGH` | unambiguous | a format string, a known algorithm's constants, an unmistakable register sequence, a vendor protocol opcode |
| `MEDIUM` | strongly implied | dataflow from a named caller, position in a named dispatch table, structural twin of a named function |
| `LOW` | used sparingly, and only by the driver | plausible but unconfirmed; prefer a SKIP |

A subagent producing `LOW` should have skipped instead.
